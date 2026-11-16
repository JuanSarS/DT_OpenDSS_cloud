# Local security demo

Los scripts de `tools/security_lab` deben ejecutarse únicamente contra
`localhost` y requieren un entorno local preparado con secretos.

Para observar tráfico deliberadamente inseguro, use un override local que
publique HTTP y no lo use en despliegues normales. En Wireshark se verá el
formulario de login, el JSON y el token.

Con Caddy en `https://localhost:8443`, Wireshark solo debe mostrar TLS. Las
credenciales, JWT, JSON y resultados no deben aparecer como plaintext.

No ejecutar estos ejemplos contra hosts públicos ni convertirlos en una
herramienta de escaneo o DDoS.
