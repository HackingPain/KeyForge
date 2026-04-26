"""Hard-coded CloudFormation template for the AWS issuer's trust policy.

Rendered by ``backend/routes/issuers_aws.py`` with ``<KEYFORGE_AWS_ACCOUNT_ID>``
and ``<YOUR_USER_ID>`` placeholders substituted (or left as-is when the
operator has not configured ``KEYFORGE_AWS_ACCOUNT_ID``, so the user knows
to ask).
"""

from __future__ import annotations

# CloudFormation template (YAML). The ExternalId condition is per-user so a
# leaked role ARN cannot be assumed by other KeyForge tenants.
AWS_TRUST_POLICY_CFN_TEMPLATE = """\
# AWS CloudFormation template - KeyForge IAM role trust policy.
# Apply this template in your AWS account, then paste the resulting role ARN
# into KeyForge under Settings -> AWS Issuer.
AWSTemplateFormatVersion: '2010-09-09'
Description: KeyForge IAM role allowing the KeyForge service account to
  assume this role and mint short-lived credentials on behalf of users.
Resources:
  KeyForgeAssumableRole:
    Type: AWS::IAM::Role
    Properties:
      RoleName: KeyForgeAssumableRole
      AssumeRolePolicyDocument:
        Version: '2012-10-17'
        Statement:
          - Effect: Allow
            Principal:
              AWS: arn:aws:iam::<KEYFORGE_AWS_ACCOUNT_ID>:root
            Action: sts:AssumeRole
            Condition:
              StringEquals:
                sts:ExternalId: <YOUR_USER_ID>
      MaxSessionDuration: 3600
      Policies:
        - PolicyName: ReadOnlyByDefault
          PolicyDocument:
            Version: '2012-10-17'
            Statement:
              - Effect: Allow
                Action:
                  - 'iam:GetUser'
                  - 'sts:GetCallerIdentity'
                Resource: '*'
Outputs:
  RoleArn:
    Description: ARN to paste back into KeyForge
    Value: !GetAtt KeyForgeAssumableRole.Arn
"""
