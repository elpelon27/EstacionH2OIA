# REPORTE TÉCNICO ZCode — 2026-10-09b: herramienta libre descarga-libros

> Canal de reportes del técnico ZCode (ver convención en
> `docs/reportes-zcode/2026-10-09-tecnico-zcode.md` y hecho #20 del grafo).

## Qué se creó (FUERA de este repo, ubicación compartida)

**`/mnt/ssd_trabajo/herramientas-libres/descarga-libros/`** — herramienta LIBRE
(pedido explícito del Líder: no aislada, acceso para cualquier skill/proyecto):

- `descarga_libros.py` — módulo/CLI de búsqueda y descarga de libros, **solo
  Python estándar** (sin venv ni dependencias): `buscar` · `pedir` (cadena
  automática) · `descargar` · `recibir` · `enviar`.
- `config.env` (chmod 600, fuera de git) — token del bot Telegram "Zlibrary"
  (@elpelon27_bot) + chat del Líder; slots opcionales para Anna's Archive
  (`AA_BASE`) y Z-Library con cuenta (`ZLIB_*`).
- `SKILL.md` — documentación de uso e integración para cualquier skill.

## Verificación (medida en vivo, 2026-10-09)

- Bot Telegram: `getMe` OK (@elpelon27_bot, nombre "Zlibrary"); `sendMessage`
  de prueba ENTREGADO al chat del Líder (id 1663148211).
- **Prueba punta a punta OK**: `pedir "manual de compostaje"` → descargó PDF
  real (687 KB, archive.org) → `sendDocument` ENTREGADO al Telegram del Líder.
- Red desde el servidor: archive.org ✅ · openlibrary.org ✅ · libgen.li/vg ✅
  (búsqueda; descarga directa anti-bot → solo fichas) · annas-archive.org NXDOMAIN
  (dominio rotado) y **.gs es un secuestro publicitario (NO usar)** · libgen.is
  resuelve pero timeout · z-lib.sk/zh.1lib.us fallan o requieren sesión.
- Hallazgo: las dos herramientas propuestas por el Líder NO sirven como módulo
  de servidor: Openlib (dstark5) es app gráfica Flutter; z-libraryopp es solo
  una página de enlaces a mirrors (riesgosa). Por eso se construyó la propia.

## Cómo la usan los skills

Ver `SKILL.md` de la herramienta. Pipeline biblioteca H2O: pedir → validar →
renombrar con prefijo → `pdfs/inbox/` → `ingest_pdf.py --once`. Si `pedir` no
descarga, imprime fichas (md5/título) pedibles a mano por el bot de Z-Library
del Líder → reenviar al bot → `descarga_libros.py recibir`.

## Pendiente (del Líder, no bloqueante)

- Dominio vigente de Anna's Archive desde su navegador → `AA_BASE` en config.env.
- (Opcional) credenciales de su cuenta Z-Library para el backend directo.

— técnico ZCode, 2026-10-09
