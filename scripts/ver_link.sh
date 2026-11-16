aws cloudformation describe-stacks `
  --stack-name opendss-thesis-main `
  --region us-east-2 `
  --profile opendss-deployer `
  --query "Stacks[0].Outputs" `
  --output table


  aws ecs describe-services `
    --cluster $Cluster `
    --services $ApiService $WorkerService `
    --region us-east-2 `
    --profile opendss-deployer `
    --query "services[].{Service:serviceName,Desired:desiredCount,Running:runningCount,Pending:pendingCount}" `
    --output table