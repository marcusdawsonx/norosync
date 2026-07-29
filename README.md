# NoroSync

Marketing reporting pipeline for the Noro Arts Shopify store.

Fetched at runtime by a scheduled Claude task:

    BASE=https://raw.githubusercontent.com/marcusdawsonx/norosync/main
    for f in RUNBOOK.md run.py schema.py render.py build_facts.py \
             build_workbook.py weekly.py; do curl -sfO "$BASE/$f"; done

Start with `RUNBOOK.md` — it lists the connector calls, the verified field IDs,
and the rules that have already cost a day of debugging each.

No credentials or secrets are stored here. The pipeline reads data through
authenticated connectors that live outside this repo.
