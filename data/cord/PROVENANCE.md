# CORD provenance

Park et al., CORD: A Consolidated Receipt Dataset for Post-OCR Parsing (2019).

Source: https://github.com/clovaai/cord and https://huggingface.co/datasets/naver-clova-ix/cord-v2

License: Creative Commons Attribution 4.0, copied as LICENSE-CC-BY. Images are public benchmark receipts.

This is a bounded demonstration subset: 48 seeded rows from the first official training parquet shard, the first 20 validation rows and the first 20 test rows. Official split membership is preserved. Seed: 11027. The training shard has 200 rows. The full benchmark is not claimed.

Original annotations, quadrilaterals, semantic categories and metadata are retained per receipt. Images are re-encoded as JPEG quality 85 for repository size. All reported real OCR runs use these committed images. Boxes are normalized by the original image dimensions. CORD dot-separated thousands amounts are normalized to decimal values. Missing labels are excluded from field metrics, rather than treated as known negatives. Label mapping is label-map.json.

Gold OCR contains annotated semantic lines and excludes some unannotated text. Real OCR sees the full image, so full-page CER/WER includes that annotation coverage mismatch.
