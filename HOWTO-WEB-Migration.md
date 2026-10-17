# Migrar la web a la ruta principal

Este documento describe cómo sustituir la web WordPress de
`https://www.ehu.eus/chemistry/theory/` por la web Hugo que ahora se prueba en
`https://www.ehu.eus/chemistry/theory/new/`, y conservar WordPress en
`https://www.ehu.eus/chemistry/theory/old/`.

En el servidor se ha identificado WordPress en
`/users/scwtcg/public_html/wordpress`. La configuración local del proyecto ya
está preparada para la URL y el destino finales:

- Host SFTP: `alweb.ehu.eus`
- Usuario: `scwtcg`
- Carpeta de publicación: `/users/scwtcg/public_html`
- URL de producción: `https://www.ehu.eus/chemistry/theory/`

Antes de mover nada o desplegar, confirma por SFTP con el administrador que
`/users/scwtcg/public_html` es el document root de
`/chemistry/theory/`, y que la instalación completa está dentro de
`wordpress/`.

## Precauciones

- Programa el cambio para un periodo de poco tráfico y avisa de una posible
  interrupción breve.
- Aunque se ha indicado `public_html/wordpress/`, verifica dónde están
  `index.php`, `wp-config.php`, `wp-content/` y `.htaccess`; puede haber reglas
  o archivos de WordPress también en la raíz.
- Haz primero una copia recuperable de **todos** los archivos del sitio y una
  copia de seguridad de la base de datos WordPress. Verifica que puedes leer
  los respaldos.
- No uses `make deploy-full` en la raíz pública. Su `mirror --delete` puede
  borrar `old/` y cualquier otro contenido que no esté en `public/`.
- No borres ni sobrescribas la instalación de WordPress hasta haber probado
  que la copia de seguridad es válida.

## 1. Inventariar y respaldar el servidor

Con SFTP, inspecciona la carpeta que sirve
`https://www.ehu.eus/chemistry/theory/` y apunta:

- Qué directorio es el document root.
- Dónde están `index.php`, `wp-config.php`, `wp-content/` y `.htaccess`,
  especialmente dentro de `wordpress/` y en la raíz.
- Si `new/` está dentro del mismo document root.
- Permisos y propietario de los archivos.

Descarga o copia el contenido completo del document root, incluidos los
archivos ocultos, a un respaldo fuera de esa carpeta. Exporta asimismo la base
de datos WordPress desde la herramienta que proporcione el servidor (por
ejemplo, phpMyAdmin). Guarda el respaldo en un lugar privado y comprueba que
los ficheros descargados tienen un tamaño razonable.

## 2. Preparar Hugo para la ruta final

La configuración ya se ha actualizado para la URL y el destino de producción:

- `hugo.yaml` y `PROD_BASEURL`: `https://www.ehu.eus/chemistry/theory/`.
- `REMOTE_PATH`: `/users/scwtcg/public_html`.
- `README.md` refleja la ruta final. `.env` es local y no debe añadirse a Git.

Las URLs de desarrollo escritas directamente en plantillas deben convertirse
en rutas generadas por Hugo. El enlace de la plantilla ISoM ya utiliza `relURL`.

Comprueba también referencias a `/wordpress/` que deban seguir funcionando
cuando WordPress viva en `/old/`. No reemplaces texto indiscriminadamente:
algunas referencias pueden ser URLs históricas o enlaces externos.

Ejecuta la búsqueda y la validación:

```bash
rg -n 'chemistry/theory/new|/wordpress/' --glob '!public/**' .
make validate
```

Revisa el sitio generado localmente antes de publicarlo. Comprueba portada,
subgrupos, páginas de publicaciones, noticias, seminarios, imágenes, PDFs y
enlaces internos. En el HTML generado no deberían quedar enlaces internos
apuntando a `/chemistry/theory/new/`.

## 3. Preparar WordPress en `/old/`

La ubicación depende de cómo esté instalado WordPress:

- **WordPress instalado en la raíz actual:** mueve los archivos y directorios
  de WordPress a `old/`, incluidos `wp-content/`, `wp-admin/`, `wp-includes/`,
  `wp-config.php`, `.htaccess` y archivos ocultos. No muevas la carpeta `new/`
  dentro de `old/`.
- **WordPress instalado en `public_html/wordpress/` (ubicación indicada):**
  mueve el contenido de esa instalación a `public_html/old/`, conservando su
  estructura interna. No crees una ruta duplicada como
  `old/wordpress/wordpress/`. Confirma antes que `wordpress/` contiene la
  instalación completa y que no hay archivos necesarios de WordPress en la
  raíz.

Si no se puede mover de forma segura con el acceso disponible, pide al
administrador de Alweb que lo haga o que confirme el método apropiado. No
ejecutes comandos recursivos de borrado para “limpiar” la raíz.

Para que WordPress funcione en la ruta nueva:

1. Cambia sus valores `home` y `siteurl` a
   `https://www.ehu.eus/chemistry/theory/old` usando el procedimiento
   recomendado por el administrador.
2. Ajusta las reglas de `.htaccess` y cualquier configuración del servidor que
   contenga la ruta anterior.
3. Si se actualizan URLs en la base de datos, utiliza `wp search-replace` o una
   herramienta que entienda los datos serializados de WordPress. No uses un
   reemplazo textual directo sobre el volcado SQL.
4. Comprueba `/old/`, `/old/wp-admin/`, imágenes y descargas. Considera también
   cómo preservar URLs antiguas como `/wordpress/wp-content/...`; pueden
   requerir redirecciones.

## 4. Publicar Hugo en la raíz pública

Haz el cambio de forma controlada:

1. Sube primero el sitio ya compilado a una carpeta temporal de staging dentro
   del espacio de la cuenta, no encima de la raíz en uso.
2. Comprueba en staging que existen `index.html`, `404.html`, `sitemap.xml`,
   recursos, imágenes y páginas de los grupos.
3. Tras confirmar que WordPress está íntegro en `old/`, deja la raíz pública
   preparada para Hugo. Debe contener los archivos generados de Hugo y la
   carpeta `old/`; no deben quedar archivos `index.php` de WordPress u otras
   reglas de WordPress interfiriendo en la portada. Conserva `.htaccess` solo
   si se ha revisado y es compatible con Hugo y con `/old/`.
4. Publica el contenido de `public/` en `/users/scwtcg/public_html/` con un
   método **incremental y sin borrado**. Revisa el destino y el listado de
   archivos antes de confirmar la operación.

El comando `make deploy` usa `lftp mirror --only-newer` y no elimina archivos
del destino. Es más seguro que `make deploy-full`, pero no limpia archivos
antiguos de WordPress que queden en la raíz ni garantiza que archivos remotos
con fechas posteriores se sobrescriban. Por tanto, no es suficiente ejecutar
`make deploy` a ciegas: primero hay que mover WordPress y revisar/preparar el
document root. Si es necesario limpiar archivos obsoletos, hazlo de forma
selectiva después del respaldo, excluyendo expresamente `old/`, o solicita la
ayuda del administrador. No actives una sincronización con `--delete` sobre
`public_html/`.

## 5. Comprobaciones y vuelta atrás

Después del cambio, prueba en una ventana privada:

- `https://www.ehu.eus/chemistry/theory/` — portada Hugo.
- URLs de los grupos y varias páginas interiores.
- CSS, JavaScript, imágenes, PDFs y descargas.
- `/old/` y `/old/wp-admin/` — WordPress conservado.
- URLs antiguas de WordPress que se decida redirigir.

Comprueba también enlaces rotos, consola del navegador y el certificado HTTPS.
Si algo esencial falla, restaura el document root desde el respaldo y avisa al
administrador; conserva `old/` hasta que el cambio esté verificado.

## Redirecciones y tareas posteriores

Decide antes del cambio qué hacer con URLs antiguas:

- Si las páginas WordPress antiguas se consultarán, mantenlas en `/old/`.
- Si hay enlaces antiguos publicados, prepara redirecciones individuales o
  reglas explícitas; no redirijas todo `/old/` a la portada nueva.
- Actualiza enlaces externos conocidos, buscadores y cualquier servicio que
  apunte a `/new/`.

La web Hugo es estática. Las noticias y seminarios con fechas futuras se
actualizan cuando se vuelve a compilar y publicar; el servidor no los cambia
por sí solo salvo que se configure una tarea programada.
