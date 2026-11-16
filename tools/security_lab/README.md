# Local security lab

Estos scripts solo aceptan `localhost` o direcciones loopback. No usar contra
Internet.

```powershell
python tools\security_lab\unauthorized_client.py --base-url https://localhost:8443
python tools\security_lab\token_tamper_demo.py --base-url https://localhost:8443
python tools\security_lab\flood_demo.py --base-url https://localhost:8443 --requests 50
```

`token_tamper_demo.py` modifica el claim `role` sin modificar la firma; el API
debe responder `401`. `flood_demo.py` tiene un máximo de 500 solicitudes y
comprueba que `/health` siga respondiendo.