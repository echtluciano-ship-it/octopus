# Octopus - Base de Clientes

## Cargar la base

```powershell
cd C:\Users\Luciano\OneDrive\Documentos\OCTOPUS
C:\Users\Luciano\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe app_octopus\data_loader.py
```

## Abrir la aplicacion

```powershell
C:\Users\Luciano\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m streamlit run app_octopus\app.py
```

Si Streamlit no esta instalado:

```powershell
C:\Users\Luciano\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m pip install streamlit
```

## Publicar con acceso privado

Recomendado para esta V1:

1. Subir la carpeta `app_octopus` a un repositorio privado.
2. Crear una Web Service en Render usando Docker.
3. Configurar estas variables privadas:

```text
OCTOPUS_APP_USER=octopus
OCTOPUS_APP_PASSWORD=una-clave-segura
```

4. Activar Cloudflare Access delante de la URL de Render para permitir solo emails autorizados.

Con esto Mariano, tu papa y vos pueden entrar desde computadora o celular. La base queda protegida por login de la app y por control de acceso externo.

Para la siguiente etapa conviene migrar `octopus.db` a PostgreSQL privado, asi todos ven una base compartida actualizable sin depender de un archivo local.

## Regla operativa V1

La lista principal oculta clientes cuya ultima operacion fue en 2025 o antes. No se borran de la base: solo se excluyen de la vista operativa para reducir ruido.
