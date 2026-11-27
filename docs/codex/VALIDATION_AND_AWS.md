# Validation baseline, evidence and AWS operations

Historical commands/results from the conversation. Verify scripts, stack/service outputs and current login before using. Never run cloud-changing operations automatically. No AWS costs assumed zero; check residual resources if user authorizes cloud cleanup. Do not re-run historical evidence by default.

## Local
```powershell
Set-Location 'F:\U\Maestria\Monitoria\Proyecto'
git status --short --branch
python -m pytest tests -q
docker version
docker compose config --quiet
docker compose ps
```
Discover correct local dependencies, virtual environment, compose flags and URLs. Do not overwrite dirty files. Test locally first. D1 historical script uses Docker image `opendss-evidence:local`; run only if requested, do not overwrite canonical evidence. Existing tests may include `tests/security/test_auth.py`; preserve auth regression and actual test layout.

## Canonical evidence references (historical)
| Deliverable | Run directory basename | Outcome |
|---|---|---|
| D1 | 20261117T050250Z_multicontext | reported PASS, exact multicontext snapshots |
| D2 | 20261116T195840Z_cloud_performance | `passed_load=false`, partial performance success |
| D3 | 20261117T043753Z_resilience | reported PASS, observed QSTS restart and security |

D1 artifacts config.json, raw_results.csv, summary.json, REPORT.md. Reported 4 models x (16 sequential + 2+4+8+16 concurrent) =184. All converged and hashes exact, max delta 0; exclude session_id and elapsed_ms. Confirm raw CSV if citing. Batch wall time includes context creation/teardown, unlike solve-only timings; avoid invalid speedup calculation. D1 is snapshot, not proof of interactive QSTS.

D2 historical PERFORMANCE_SUMMARY.json (verify locally):
| Metric | 5 users | 10 users |
|---|---:|---:|
| Requests | 1861 | 1889 |
| Failures | 0 | 1 |
| RPS | 10.4933 | 10.5259 |
| Mean ms | 344.3179 | 792.9877 |
| p50 ms | 170 | 320 |
| p95 ms | 1100 | 2500 |
| p99 ms | 1600 | 3200 |
| Max ms | 2678.2758 | 4587.8207 |
CPU mean of averages 52.038%, peak 99.767%; memory 31.519%, peak 83.398%; 9 samples each. Scaling timeline 32 samples, desired min/max 1/4, running min/max 1/3. One DELETE cleanup 502; no claim of full formal performance pass. Nested `20261116T195849Z_cloud_mvp` PASS, two authenticated concurrent users REST/WS IEEE123 and IEEE8500. Preserve CSV/JSON/logs and actual criterion.

D3 summary reported: resilience_passed=true, observed_qsts_restart=true, security_passed=true, passed=true. Nested security `20261117T044914Z_security`: expected unauthorized REST 401, unrelated user 403, viewer read 200 / control 403, admin metrics 200, third concurrent job admission 429, cleanup 204, rate limiting 429, health 200. Preserve original ws_events.jsonl, resilience_result.json, SUMMARY.json, REPORT.md and ECS task/service evidence. No exact recovery latency or multiple concurrent unaffected jobs established without inspecting evidence. Do not leak historical AWS account IDs, task ARNs or internal IPs unnecessarily.

## AWS environment (historical)
Profile `opendss-deployer`, region `us-east-2`, account on AWS Free Plan/credits. Billing plan check historically uses us-east-1. Keep minimal cost, no Organizations/IAM Identity Center changes (may affect Free Plan), no NAT or unnecessary paid managed services. Never store credentials in code or print secrets. AWS CLI was v2.40.3; verify locally. Login only if user requests cloud validation; no automatic deployment. Commands:
```powershell
aws --version
aws login --profile opendss-deployer
$env:AWS_PROFILE = 'opendss-deployer'
$env:AWS_REGION = 'us-east-2'
$env:AWS_DEFAULT_REGION = 'us-east-2'
aws sts get-caller-identity
aws freetier get-account-plan-state --region us-east-1
```
Read-only diagnostics (with explicit user authorization for AWS access; actual names from stack outputs):
```powershell
aws cloudformation list-stacks --query "StackSummaries[?StackStatus!='DELETE_COMPLETE'].[StackName,StackStatus]" --output table
aws cloudformation describe-stacks --stack-name opendss-thesis-main --query 'Stacks[0].Outputs' --output table
aws ecs list-clusters --output table
aws ecs list-services --cluster opendss-thesis-cluster --output table
aws ecs describe-services --cluster opendss-thesis-cluster --services opendss-thesis-worker --query 'services[0].{Desired:desiredCount,Running:runningCount,Pending:pendingCount}' --output table
aws ecs list-tasks --cluster opendss-thesis-cluster --service-name opendss-thesis-worker --desired-status RUNNING --output table
aws ecs describe-services --cluster opendss-thesis-cluster --services opendss-thesis-worker --query 'services[0].events[0:15].[createdAt,message]' --output table
aws logs tail '/opendss/opendss-thesis/api-manager' --since 30m --format short
aws logs tail '/opendss/opendss-thesis/simulation-worker' --since 30m --format short
aws application-autoscaling describe-scaling-activities --service-namespace ecs --output table
aws cloudfront list-distributions --query 'DistributionList.Items[].{Id:Id,Domain:DomainName,Status:Status}' --output table
aws elbv2 describe-load-balancers --output table
aws efs describe-file-systems --output table
aws ecr describe-repositories --output table
aws servicediscovery list-namespaces --output table
aws secretsmanager list-secrets --query 'SecretList[].{Name:Name}' --output table
```
Do not use `get-secret-value` for routine debugging. Inspect actual stack outputs rather than guessing service names.

## Historical scripts (reference only, not to run without authorization)
```powershell
# D1 local evidence
.\scripts\run_deliverable1_evidence.ps1
# Normal deployment
.\scripts\deploy_cloud.ps1 -Profile opendss-deployer
# D2 performance deployment and evidence
.\scripts\deploy_cloud.ps1 -Profile opendss-deployer -ReuseImages -PerformanceMode -WorkerCount 1 -WorkerMinCount 1 -WorkerMaxCount 6 -SkipSmoke
.\scripts\run_deliverable2_cloud_evidence.ps1 -Profile opendss-deployer -LoadSeconds 180
# D3 deployment flags: verify script and choose correct worker count before use
.\scripts\deploy_cloud.ps1 -Profile opendss-deployer -ResilienceMode -WorkerCount 3 -WorkerMinCount 1 -WorkerMaxCount 6 -SkipSmoke
.\scripts\run_deliverable3_cloud_evidence.ps1 -Profile opendss-deployer
.\scripts\smoke_cloud.ps1 -Profile opendss-deployer
python .\scripts\build_evidence_index.py
# Destructive teardown, only with explicit confirmation and after collecting evidence
.\scripts\destroy_cloud.ps1 -Profile opendss-deployer
```
`-ReuseImages` is only appropriate when images match intended code/commit. Fresh code generally needs new images. After authorized teardown verify CloudFormation, active ECS tasks/services, CloudFront, ALB, EFS, ECR, log groups, secrets and other residual billable resources; tagged inactive task definitions alone do not imply running cost. Do not claim cloud currently destroyed or deployed without inspection. No deployment required for the initial bugfix phase.
