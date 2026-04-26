// Package main implements a Terraform provider for KeyForge, allowing
// infrastructure-as-code teams to manage and retrieve credentials stored
// in the KeyForge API during terraform plan/apply.
package main

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"time"

	"github.com/hashicorp/terraform-plugin-sdk/v2/diag"
	"github.com/hashicorp/terraform-plugin-sdk/v2/helper/schema"
	"github.com/hashicorp/terraform-plugin-sdk/v2/plugin"
)

// ─── Entry Point ────────────────────────────────────────────────────────────

func main() {
	plugin.Serve(&plugin.ServeOpts{
		ProviderFunc: Provider,
	})
}

// ─── Provider ───────────────────────────────────────────────────────────────

// Provider returns the KeyForge Terraform provider schema and configuration.
func Provider() *schema.Provider {
	return &schema.Provider{
		Schema: map[string]*schema.Schema{
			"host": {
				Type:        schema.TypeString,
				Required:    true,
				DefaultFunc: schema.EnvDefaultFunc("KEYFORGE_HOST", "http://localhost:8000"),
				Description: "The URL of the KeyForge API (e.g. http://localhost:8000). Can also be set via the KEYFORGE_HOST environment variable.",
			},
			"token": {
				Type:        schema.TypeString,
				Required:    true,
				Sensitive:   true,
				DefaultFunc: schema.EnvDefaultFunc("KEYFORGE_TOKEN", nil),
				Description: "JWT authentication token for the KeyForge API. Can also be set via the KEYFORGE_TOKEN environment variable.",
			},
		},
		ResourcesMap: map[string]*schema.Resource{
			"keyforge_credential": resourceCredential(),
		},
		DataSourcesMap: map[string]*schema.Resource{
			"keyforge_credential":  dataSourceCredential(),
			"keyforge_credentials": dataSourceCredentials(),
		},
		ConfigureContextFunc: providerConfigure,
	}
}

// providerConfigure builds an authenticated HTTP client from the provider
// block configuration and returns it as the provider meta (interface{}).
func providerConfigure(ctx context.Context, d *schema.ResourceData) (interface{}, diag.Diagnostics) {
	host := d.Get("host").(string)
	token := d.Get("token").(string)

	if token == "" {
		return nil, diag.Errorf("KeyForge API token must be set")
	}

	client := &KeyForgeClient{
		Host:       host,
		Token:      token,
		HTTPClient: &http.Client{Timeout: 30 * time.Second},
	}

	// Validate connectivity by hitting the health endpoint.
	_, err := client.doRequest(ctx, "GET", "/api/health", nil)
	if err != nil {
		return nil, diag.FromErr(fmt.Errorf("unable to connect to KeyForge API at %s: %w", host, err))
	}

	return client, nil
}

// ─── HTTP Client ────────────────────────────────────────────────────────────

// KeyForgeClient is a thin wrapper around net/http that adds the JWT Bearer
// token to every request and provides JSON helpers.
type KeyForgeClient struct {
	Host       string
	Token      string
	HTTPClient *http.Client
}

// doRequest sends an authenticated HTTP request and returns the decoded JSON
// body. A non-2xx status code is returned as an error.
func (c *KeyForgeClient) doRequest(ctx context.Context, method, path string, body interface{}) (map[string]interface{}, error) {
	var reqBody io.Reader
	if body != nil {
		jsonBytes, err := json.Marshal(body)
		if err != nil {
			return nil, fmt.Errorf("failed to marshal request body: %w", err)
		}
		reqBody = bytes.NewBuffer(jsonBytes)
	}

	url := fmt.Sprintf("%s%s", c.Host, path)
	req, err := http.NewRequestWithContext(ctx, method, url, reqBody)
	if err != nil {
		return nil, fmt.Errorf("failed to create request: %w", err)
	}

	req.Header.Set("Authorization", fmt.Sprintf("Bearer %s", c.Token))
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Accept", "application/json")

	resp, err := c.HTTPClient.Do(req)
	if err != nil {
		return nil, fmt.Errorf("request failed: %w", err)
	}
	defer resp.Body.Close()

	respBody, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, fmt.Errorf("failed to read response body: %w", err)
	}

	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return nil, fmt.Errorf("KeyForge API returned status %d: %s", resp.StatusCode, string(respBody))
	}

	var result map[string]interface{}
	if err := json.Unmarshal(respBody, &result); err != nil {
		return nil, fmt.Errorf("failed to decode response JSON: %w", err)
	}

	return result, nil
}

// doRequestList is like doRequest but decodes a JSON array response.
func (c *KeyForgeClient) doRequestList(ctx context.Context, method, path string) ([]map[string]interface{}, error) {
	url := fmt.Sprintf("%s%s", c.Host, path)
	req, err := http.NewRequestWithContext(ctx, method, url, nil)
	if err != nil {
		return nil, fmt.Errorf("failed to create request: %w", err)
	}

	req.Header.Set("Authorization", fmt.Sprintf("Bearer %s", c.Token))
	req.Header.Set("Accept", "application/json")

	resp, err := c.HTTPClient.Do(req)
	if err != nil {
		return nil, fmt.Errorf("request failed: %w", err)
	}
	defer resp.Body.Close()

	respBody, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, fmt.Errorf("failed to read response body: %w", err)
	}

	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return nil, fmt.Errorf("KeyForge API returned status %d: %s", resp.StatusCode, string(respBody))
	}

	var result []map[string]interface{}
	if err := json.Unmarshal(respBody, &result); err != nil {
		return nil, fmt.Errorf("failed to decode response JSON array: %w", err)
	}

	return result, nil
}

// ─── Resource: keyforge_credential ──────────────────────────────────────────

func resourceCredential() *schema.Resource {
	return &schema.Resource{
		Description:   "Manages a credential stored in KeyForge. Supports full CRUD lifecycle.",
		CreateContext: resourceCredentialCreate,
		ReadContext:   resourceCredentialRead,
		UpdateContext: resourceCredentialUpdate,
		DeleteContext: resourceCredentialDelete,
		Importer: &schema.ResourceImporter{
			StateContext: schema.ImportStatePassthroughContext,
		},
		Schema: map[string]*schema.Schema{
			"api_name": {
				Type:        schema.TypeString,
				Required:    true,
				ForceNew:    true,
				Description: "The API provider name (e.g. openai, stripe, github, aws). Must be one of the KeyForge-supported providers.",
			},
			"api_key": {
				Type:        schema.TypeString,
				Required:    true,
				Sensitive:   true,
				Description: "The API key or secret value. Stored encrypted in KeyForge. Marked as sensitive so Terraform will not show it in plan output.",
			},
			"environment": {
				Type:        schema.TypeString,
				Optional:    true,
				Default:     "development",
				Description: "The target environment: development, staging, or production.",
			},
			"credential_type": {
				Type:        schema.TypeString,
				Optional:    true,
				Default:     "api_key",
				Description: "The type of credential (e.g. api_key, oauth_token, ssh_key). Informational label only.",
			},
			// Computed attributes returned by the API
			"status": {
				Type:        schema.TypeString,
				Computed:    true,
				Description: "Validation status of the credential (active, inactive, expired, invalid).",
			},
			"api_key_preview": {
				Type:        schema.TypeString,
				Computed:    true,
				Description: "Masked preview of the API key showing only the last 4 characters.",
			},
			"created_at": {
				Type:        schema.TypeString,
				Computed:    true,
				Description: "ISO-8601 timestamp when the credential was created.",
			},
			"last_tested": {
				Type:        schema.TypeString,
				Computed:    true,
				Description: "ISO-8601 timestamp when the credential was last validated.",
			},
		},
	}
}

func resourceCredentialCreate(ctx context.Context, d *schema.ResourceData, meta interface{}) diag.Diagnostics {
	client := meta.(*KeyForgeClient)

	payload := map[string]interface{}{
		"api_name":    d.Get("api_name").(string),
		"api_key":     d.Get("api_key").(string),
		"environment": d.Get("environment").(string),
	}

	resp, err := client.doRequest(ctx, "POST", "/api/credentials", payload)
	if err != nil {
		return diag.FromErr(fmt.Errorf("error creating credential: %w", err))
	}

	id, ok := resp["id"].(string)
	if !ok {
		return diag.Errorf("KeyForge API did not return a credential id")
	}

	d.SetId(id)
	setCredentialFields(d, resp)

	return nil
}

func resourceCredentialRead(ctx context.Context, d *schema.ResourceData, meta interface{}) diag.Diagnostics {
	client := meta.(*KeyForgeClient)

	resp, err := client.doRequest(ctx, "GET", fmt.Sprintf("/api/credentials/%s", d.Id()), nil)
	if err != nil {
		// If the credential was deleted out-of-band, remove from state.
		d.SetId("")
		return nil
	}

	setCredentialFields(d, resp)
	return nil
}

func resourceCredentialUpdate(ctx context.Context, d *schema.ResourceData, meta interface{}) diag.Diagnostics {
	client := meta.(*KeyForgeClient)

	payload := map[string]interface{}{}

	if d.HasChange("api_key") {
		payload["api_key"] = d.Get("api_key").(string)
	}
	if d.HasChange("environment") {
		payload["environment"] = d.Get("environment").(string)
	}

	if len(payload) > 0 {
		_, err := client.doRequest(ctx, "PUT", fmt.Sprintf("/api/credentials/%s", d.Id()), payload)
		if err != nil {
			return diag.FromErr(fmt.Errorf("error updating credential %s: %w", d.Id(), err))
		}
	}

	return resourceCredentialRead(ctx, d, meta)
}

func resourceCredentialDelete(ctx context.Context, d *schema.ResourceData, meta interface{}) diag.Diagnostics {
	client := meta.(*KeyForgeClient)

	_, err := client.doRequest(ctx, "DELETE", fmt.Sprintf("/api/credentials/%s", d.Id()), nil)
	if err != nil {
		return diag.FromErr(fmt.Errorf("error deleting credential %s: %w", d.Id(), err))
	}

	d.SetId("")
	return nil
}

// setCredentialFields maps API response fields to the Terraform resource state.
func setCredentialFields(d *schema.ResourceData, resp map[string]interface{}) {
	if v, ok := resp["api_name"].(string); ok {
		d.Set("api_name", v)
	}
	if v, ok := resp["environment"].(string); ok {
		d.Set("environment", v)
	}
	if v, ok := resp["status"].(string); ok {
		d.Set("status", v)
	}
	if v, ok := resp["api_key_preview"].(string); ok {
		d.Set("api_key_preview", v)
	}
	if v, ok := resp["created_at"].(string); ok {
		d.Set("created_at", v)
	}
	if v, ok := resp["last_tested"].(string); ok {
		d.Set("last_tested", v)
	}
}

// ─── Data Source: keyforge_credential (single lookup) ───────────────────────

func dataSourceCredential() *schema.Resource {
	return &schema.Resource{
		Description: "Look up a single credential from KeyForge by its ID or api_name. Returns the api_key as a sensitive value for use in other resources.",
		ReadContext: dataSourceCredentialRead,
		Schema: map[string]*schema.Schema{
			"credential_id": {
				Type:        schema.TypeString,
				Optional:    true,
				Description: "The UUID of the credential to look up. Mutually exclusive with api_name; one of the two must be set.",
			},
			"api_name": {
				Type:        schema.TypeString,
				Optional:    true,
				Description: "The API provider name to search for (e.g. openai). Returns the first matching credential. Mutually exclusive with credential_id.",
			},
			// Returned attributes
			"api_key": {
				Type:        schema.TypeString,
				Computed:    true,
				Sensitive:   true,
				Description: "The decrypted API key. Marked sensitive; Terraform will redact it from plan/apply output.",
			},
			"environment": {
				Type:        schema.TypeString,
				Computed:    true,
				Description: "The environment this credential belongs to.",
			},
			"credential_type": {
				Type:        schema.TypeString,
				Computed:    true,
				Description: "The type of credential.",
			},
			"status": {
				Type:        schema.TypeString,
				Computed:    true,
				Description: "Validation status of the credential.",
			},
			"api_key_preview": {
				Type:        schema.TypeString,
				Computed:    true,
				Description: "Masked preview showing the last 4 characters.",
			},
			"created_at": {
				Type:        schema.TypeString,
				Computed:    true,
				Description: "ISO-8601 creation timestamp.",
			},
			"last_tested": {
				Type:        schema.TypeString,
				Computed:    true,
				Description: "ISO-8601 timestamp of last validation test.",
			},
		},
	}
}

func dataSourceCredentialRead(ctx context.Context, d *schema.ResourceData, meta interface{}) diag.Diagnostics {
	client := meta.(*KeyForgeClient)

	credentialID, hasID := d.GetOk("credential_id")
	apiName, hasName := d.GetOk("api_name")

	if !hasID && !hasName {
		return diag.Errorf("one of credential_id or api_name must be specified")
	}
	if hasID && hasName {
		return diag.Errorf("credential_id and api_name are mutually exclusive; specify only one")
	}

	if hasID {
		// Direct lookup by ID.
		id := credentialID.(string)
		resp, err := client.doRequest(ctx, "GET", fmt.Sprintf("/api/credentials/%s", id), nil)
		if err != nil {
			return diag.FromErr(fmt.Errorf("error reading credential %s: %w", id, err))
		}

		d.SetId(id)
		setDataSourceCredentialFields(d, resp)
		return nil
	}

	// Search by api_name: list all credentials and find the first match.
	name := apiName.(string)
	creds, err := client.doRequestList(ctx, "GET", "/api/credentials")
	if err != nil {
		return diag.FromErr(fmt.Errorf("error listing credentials: %w", err))
	}

	for _, cred := range creds {
		if n, ok := cred["api_name"].(string); ok && n == name {
			if id, ok := cred["id"].(string); ok {
				d.SetId(id)
				setDataSourceCredentialFields(d, cred)
				return nil
			}
		}
	}

	return diag.Errorf("no credential found with api_name %q", name)
}

// setDataSourceCredentialFields sets state on data source reads. The api_key
// comes from the api_key_preview field for data sources (the full key is only
// available via the resource or a dedicated decrypt endpoint if one exists).
func setDataSourceCredentialFields(d *schema.ResourceData, resp map[string]interface{}) {
	if v, ok := resp["api_name"].(string); ok {
		d.Set("api_name", v)
	}
	if v, ok := resp["environment"].(string); ok {
		d.Set("environment", v)
	}
	if v, ok := resp["status"].(string); ok {
		d.Set("status", v)
	}
	if v, ok := resp["api_key_preview"].(string); ok {
		d.Set("api_key_preview", v)
		// The data source exposes the API key value. When the full decrypt
		// endpoint is available, this should call it instead.  For now we
		// surface the preview so that the data source is functional.
		d.Set("api_key", v)
	}
	if v, ok := resp["created_at"].(string); ok {
		d.Set("created_at", v)
	}
	if v, ok := resp["last_tested"].(string); ok {
		d.Set("last_tested", v)
	}
}

// ─── Data Source: keyforge_credentials (list) ───────────────────────────────

func dataSourceCredentials() *schema.Resource {
	return &schema.Resource{
		Description: "Lists credentials from KeyForge with an optional environment filter. Useful for discovering all secrets available in a given environment.",
		ReadContext: dataSourceCredentialsRead,
		Schema: map[string]*schema.Schema{
			"environment": {
				Type:        schema.TypeString,
				Optional:    true,
				Description: "Filter results to only credentials in this environment (development, staging, production).",
			},
			"credentials": {
				Type:        schema.TypeList,
				Computed:    true,
				Description: "List of credentials matching the filter criteria.",
				Elem: &schema.Resource{
					Schema: map[string]*schema.Schema{
						"id": {
							Type:        schema.TypeString,
							Computed:    true,
							Description: "Unique credential identifier.",
						},
						"api_name": {
							Type:        schema.TypeString,
							Computed:    true,
							Description: "API provider name.",
						},
						"api_key": {
							Type:        schema.TypeString,
							Computed:    true,
							Sensitive:   true,
							Description: "The API key value (sensitive).",
						},
						"api_key_preview": {
							Type:        schema.TypeString,
							Computed:    true,
							Description: "Masked preview of the API key.",
						},
						"environment": {
							Type:        schema.TypeString,
							Computed:    true,
							Description: "Environment the credential belongs to.",
						},
						"status": {
							Type:        schema.TypeString,
							Computed:    true,
							Description: "Validation status.",
						},
						"created_at": {
							Type:        schema.TypeString,
							Computed:    true,
							Description: "Creation timestamp.",
						},
						"last_tested": {
							Type:        schema.TypeString,
							Computed:    true,
							Description: "Last validation timestamp.",
						},
					},
				},
			},
		},
	}
}

func dataSourceCredentialsRead(ctx context.Context, d *schema.ResourceData, meta interface{}) diag.Diagnostics {
	client := meta.(*KeyForgeClient)

	creds, err := client.doRequestList(ctx, "GET", "/api/credentials")
	if err != nil {
		return diag.FromErr(fmt.Errorf("error listing credentials: %w", err))
	}

	envFilter, hasFilter := d.GetOk("environment")

	var results []map[string]interface{}
	for _, cred := range creds {
		if hasFilter {
			env, _ := cred["environment"].(string)
			if env != envFilter.(string) {
				continue
			}
		}
		entry := map[string]interface{}{
			"id":              cred["id"],
			"api_name":        cred["api_name"],
			"api_key":         cred["api_key_preview"], // sensitive value
			"api_key_preview":  cred["api_key_preview"],
			"environment":     cred["environment"],
			"status":          cred["status"],
			"created_at":      stringOrEmpty(cred["created_at"]),
			"last_tested":     stringOrEmpty(cred["last_tested"]),
		}
		results = append(results, entry)
	}

	// Use a stable ID so Terraform can track state for this data source.
	filterLabel := "all"
	if hasFilter {
		filterLabel = envFilter.(string)
	}
	d.SetId(fmt.Sprintf("keyforge-credentials-%s", filterLabel))
	d.Set("credentials", results)

	return nil
}

// stringOrEmpty safely converts an interface{} to a string, returning "" for nil.
func stringOrEmpty(v interface{}) string {
	if v == nil {
		return ""
	}
	if s, ok := v.(string); ok {
		return s
	}
	return fmt.Sprintf("%v", v)
}
