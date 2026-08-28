# Data sources and third-party licensing

The [LICENSE](LICENSE) covers **the code in this repository**. It does not, and
cannot, cover the third-party data the repository redistributes or that the
pipeline consumes. Each source below carries its own terms.

---

## Qur'anic text — redistributed in this repository

**`Data/raw/quran-uthmani.txt`**

> Tanzil Qur'an Text (Uthmani, version 1.0.2)
> Copyright © 2008–2010 [Tanzil.net](https://tanzil.net)
> License: **Creative Commons Attribution 3.0**

Terms that bind any use of this repository:

- Verbatim copies may be distributed. **Changing the text is not permitted.**
- The source (Tanzil.net) must be clearly indicated, with a link to
  <https://tanzil.net> so users can track changes.
- The copyright block must be preserved in all copies. It is retained at the end
  of the file — **do not strip it.**

## Tajwīd rule annotations — redistributed in this repository

**`Data/raw/tajweed.hafs.uthmani-pause-sajdah.json`**

Character-offset annotations of tajwīd rules, keyed to the Uthmani text above.
The file carries no embedded licence header.

> ⚠️ **To verify.** The filename matches the output format of the open-source
> `quran-tajweed` project. The exact provenance and licence of this copy have not
> been confirmed, and should be before this repository is relied on commercially.

## Acoustic model — downloaded at runtime, not redistributed

**`jonatasgrosman/wav2vec2-large-xlsr-53-arabic`**, fetched from the Hugging Face
Hub. Not vendored here. Refer to the
[model card](https://huggingface.co/jonatasgrosman/wav2vec2-large-xlsr-53-arabic)
for its licence and for the licences of the datasets it was fine-tuned on.

## Reciter audio — not in this repository

~36 GB across 30 reciters, consumed locally by the ETL. **No audio is committed
here**, only the code that processes it and the calibration figures it produced.

> ⚠️ **To verify.** Recordings of Qur'anic recitation carry the rights of the
> reciter and of whoever published them. These vary by reciter and by source.
> Redistributing them — or shipping them inside a product — needs those rights
> checked individually.

---

## What this means in practice

**Reading, running and studying this repository** is unencumbered, provided the
Tanzil attribution stays intact.

**Building a product on it** requires resolving the two items marked *to verify*
above. The engine and the pipeline are mine to license; the corpus and the
recitations are not.
