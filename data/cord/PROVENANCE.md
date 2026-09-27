# CORD provenance

Park et al., CORD: A Consolidated Receipt Dataset for Post-OCR Parsing (2019).

Source: https://github.com/clovaai/cord and https://huggingface.co/datasets/naver-clova-ix/cord-v2

License: Creative Commons Attribution 4.0, copied as LICENSE-CC-BY. Images are public benchmark receipts.

All official CORD v2 rows are included: 800 training, 100 validation and 100 test receipts. Every row from all four training shards and the validation/test shards is retained, in upstream order. Official split membership is preserved and verified against each annotation's metadata (the original `valid` alias maps to `validation`); no sampling or repartitioning occurs. Pinned dataset revision: `7f0115a4b758a71d6473b8d085751692da2fef98`. Each original parquet's SHA-256 and row count is in source-manifest.json.

Original annotations, quadrilaterals, semantic categories and metadata are retained per receipt. Images are re-encoded as JPEG quality 85 for repository size. All reported real OCR runs use these committed images. Boxes are normalized by the original image dimensions. CORD dot-separated thousands amounts are normalized to decimal values. Missing labels are excluded from field metrics, rather than treated as known negatives. Label mapping is label-map.json.

Gold OCR contains annotated semantic lines and excludes some unannotated text. Real OCR sees the full image, so full-page CER/WER includes that annotation coverage mismatch.

Normalization revision 2 removes the Indonesian `Rp.` currency prefix before numeric parsing. Repeated identical monetary labels resolve to one scalar, while conflicting lists and unparseable values remain unknown. This changes only normalized labels, never original annotations or committed image bytes. Missing targets must be excluded from that target's evaluation denominator.
