import { useState, useEffect } from "react";

const CostEstimation = ({ api }) => {
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [selectedApi, setSelectedApi] = useState(null);
  const [detail, setDetail] = useState(null);

  useEffect(() => { fetchSummary(); }, []);

  const fetchSummary = async () => {
    setLoading(true);
    try {
      const response = await api.get('/cost-estimation/summary');
      setSummary(response.data);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to load cost estimation.');
    } finally {
      setLoading(false);
    }
  };

  const fetchDetail = async (apiName) => {
    setSelectedApi(apiName);
    try {
      const response = await api.get(`/cost-estimation/${apiName}`);
      setDetail(response.data);
    } catch (err) {
      setDetail({ error: err.response?.data?.detail || 'No pricing data available.' });
    }
  };

  const formatCost = (cost) => {
    if (cost === null || cost === undefined) return 'Usage-based';
    return `$${cost.toFixed(2)}/mo`;
  };

  return (
    <div className="bg-white rounded-lg shadow-md p-6">
      <h2 className="text-2xl font-bold text-gray-900 mb-6">Cost Estimation</h2>

      {error && (
        <div className="mb-4 bg-red-50 border border-red-200 rounded-lg p-4">
          <p className="text-sm text-red-700">{error}</p>
        </div>
      )}

      {loading ? (
        <div className="flex justify-center items-center h-32">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-600"></div>
        </div>
      ) : summary ? (
        <div>
          {/* Summary Card */}
          <div className="bg-indigo-50 rounded-lg p-6 mb-6">
            <p className="text-sm text-indigo-600 font-medium">Estimated Monthly Minimum</p>
            <p className="text-4xl font-bold text-indigo-900">${summary.total_estimated_monthly_minimum?.toFixed(2) || '0.00'}</p>
            <p className="text-sm text-indigo-500 mt-1">{summary.services_counted} service(s) tracked</p>
          </div>

          {/* Service Breakdown */}
          <h3 className="font-semibold text-gray-900 mb-3">Service Breakdown</h3>
          <div className="space-y-2">
            {(summary.services || []).map((svc) => (
              <div
                key={svc.api_name}
                onClick={() => fetchDetail(svc.api_name)}
                className="flex justify-between items-center border border-gray-200 rounded-lg p-4 cursor-pointer hover:border-indigo-300 transition"
              >
                <div>
                  <p className="font-medium text-gray-900">{svc.name}</p>
                  <p className="text-xs text-gray-500">{svc.pricing_model}</p>
                </div>
                <div className="text-right">
                  <p className="font-semibold text-gray-900">{formatCost(svc.estimated_monthly_cost)}</p>
                  {svc.note && <p className="text-xs text-gray-500">{svc.note}</p>}
                </div>
              </div>
            ))}
          </div>

          {/* Detail Panel */}
          {detail && selectedApi && (
            <div className="mt-6 border border-indigo-200 rounded-lg p-4 bg-indigo-50">
              <div className="flex justify-between items-start">
                <h3 className="font-semibold text-indigo-900">{detail.name || selectedApi} Pricing Details</h3>
                <button onClick={() => { setDetail(null); setSelectedApi(null); }} className="text-indigo-500 text-sm">Close</button>
              </div>
              {detail.error ? (
                <p className="text-sm text-red-600 mt-2">{detail.error}</p>
              ) : (
                <div className="mt-3">
                  {detail.tiers && (
                    <div className="space-y-2">
                      {detail.tiers.map((tier, i) => (
                        <div key={i} className="bg-white rounded p-3">
                          <p className="font-medium text-sm">{tier.name}</p>
                          {tier.monthly_cost !== undefined && <p className="text-sm text-gray-600">${tier.monthly_cost}/month</p>}
                          {tier.input_per_1m !== undefined && (
                            <p className="text-xs text-gray-500">Input: ${tier.input_per_1m}/1M tokens, Output: ${tier.output_per_1m}/1M tokens</p>
                          )}
                          {tier.limits && <p className="text-xs text-gray-500">{tier.limits}</p>}
                        </div>
                      ))}
                    </div>
                  )}
                  {detail.rate && <p className="text-sm text-gray-700 mt-2">Rate: {detail.rate}</p>}
                  {detail.free_tier && <p className="text-sm text-green-700 mt-2">Free tier: {detail.free_tier}</p>}
                  {detail.docs_url && (
                    <a href={detail.docs_url} target="_blank" rel="noopener noreferrer" className="text-sm text-indigo-600 hover:underline mt-2 inline-block">
                      View pricing docs
                    </a>
                  )}
                </div>
              )}
            </div>
          )}
        </div>
      ) : (
        <div className="text-center py-12 text-gray-500">
          <p>No cost data available. Add credentials to see estimated costs.</p>
        </div>
      )}
    </div>
  );
};

export default CostEstimation;
