aws cloudformation describe-stacks `
  --stack-name opendss-thesis-main `
  --region us-east-2 `
  --profile opendss-deployer `
  --query "Stacks[0].Outputs" `
  --output table