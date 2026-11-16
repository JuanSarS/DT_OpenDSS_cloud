# IAM para despliegue AWS

## Separación de identidades

### Identidad de despliegue
Se usa únicamente desde el PC para ejecutar AWS CLI/CloudFormation. Para el laboratorio de tesis puede tener temporalmente `AdministratorAccess` para evitar una política incompleta durante los ciclos crear/destruir. No uses el usuario root.

AWS recomienda preferir credenciales temporales mediante IAM Identity Center/SSO sobre access keys de larga duración.

### ECS Task Execution Role
Lo crea `main.yaml`. ECS lo usa para:
- pull de imágenes ECR;
- escritura de logs;
- lectura de los tres secretos de Secrets Manager.

No es una credencial del código de negocio.

### Task roles de aplicación
La versión actual no requiere permisos AWS desde el código: el discovery usa DNS de Cloud Map, EFS se monta por plataforma y secretos se inyectan por ECS. Por ello no se entrega un role de aplicación con permisos amplios.

## Access key si no hay SSO

Crear una access key únicamente para un IAM user dedicado de despliegue:

1. IAM > Users > usuario dedicado.
2. Security credentials.
3. Create access key.
4. CLI.
5. Descargar CSV.
6. Importar con `aws configure import --csv file://...` o configurar perfil con `aws configure --profile opendss-deployer`.

Nunca guardes el CSV ni las credenciales en este repositorio.

## Verificación

```powershell
aws sts get-caller-identity --profile opendss-deployer
```

El ARN mostrado debe corresponder a la identidad de despliegue esperada.
