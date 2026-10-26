# Project Notes

## Overview

This project classifies 100 comments into three categories: acceptable, toxic, and spam, using Cloudflare Workers AI and the clef-flash model.

## Files

- `comments.json` — Input dataset containing the comments.
- `classify_comments.py` — Python script used to classify the comments.
- `report.html` — Generated HTML report containing the classifications and confidence scores.
- `MISTAKES.md` — Notes about potential misclassifications identified during review.
- `cloud-flare.local.sh` — Local configuration for API credentials. This file must not be committed or pushed to GitHub.

## Requirements

- Python 3
- Cloudflare Workers AI API access and valid credentials
- Internet connection to access the API

## How to Run

1. Open a terminal in the project directory.
2. Load the local Cloudflare configuration.
3. Run the classification script.

```bash
source ./cloud-flare.local.sh
python3 classify_comments.py
```

The script processes the comments and generates `report.html`.

## Manual Review

The generated report should be reviewed manually to check whether the predicted labels match the intended categories. Confidence scores are useful indicators, but they do not guarantee correct classifications.

Potential misclassifications identified during review are documented in `MISTAKES.md`.

## Security

API credentials must remain local and must never be committed to the public repository.
