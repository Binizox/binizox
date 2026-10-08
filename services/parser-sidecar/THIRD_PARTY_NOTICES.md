# Third Party Notices

## RAGFlow

- Project: https://github.com/infiniflow/ragflow
- Commit: `313ca90f6abd7682fe8523e16fd67b3653a3fa84`
- Source: `deepdoc/parser/pdf_parser.py`, `PlainParser`
- License: Apache License 2.0
- Local file: `app/vendor/ragflow_plain_pdf.py`

The local copy retains the original copyright and license header. It removes
RAGFlow platform imports, preserves per-page text instead of flattening all
lines, and propagates parse failures to the sidecar contract.
