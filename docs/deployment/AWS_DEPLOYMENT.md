# Despliegue AWS

La guía operativa canónica es [`AWS_ONE_CLICK.md`](AWS_ONE_CLICK.md).

## Comandos principales

```powershell
.\scripts\deploy_cloud.ps1 -Profile opendss-deployer
```

```powershell
.\scripts\destroy_cloud.ps1 -Profile opendss-deployer
```

## Archivos de infraestructura

- `infra/aws/cloudformation/bootstrap.yaml`: ECR + Secrets Manager.
- `infra/aws/cloudformation/main.yaml`: VPC, SG, EFS, Cloud Map, ECS/Fargate, ALB, CloudFront, logs y auto scaling.
- `infra/aws/cloudformation/parameters.example.json`: valores de referencia/documentación.

No edites recursos manualmente en AWS para un despliegue normal; los cambios deben quedar en CloudFormation.
