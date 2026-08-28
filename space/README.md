---
title: Sanad — Tajweed Correction
emoji: 📖
colorFrom: green
colorTo: gray
sdk: gradio
sdk_version: 6.26.0
app_file: app.py
pinned: false
license: mit
short_description: Tajweed correction for Qur'anic recitation
---

# Sanad

Public demo of the tajwīd correction engine from
[github.com/harounRhim/sanad](https://github.com/harounRhim/sanad).

Forced-aligns `wav2vec2-large-xlsr-53-arabic` against the reference verse, then
measures each annotated segment: duration in ḥarakāt for `madd` rules, plus a
nasality score for `ghunnah` rules.

Scoped to sūrahs 105–114 and to āyāt carrying a `madd_2` anchor — see the note
at the bottom of the app for why.

**Assistive practice tool.** Not a replacement for a qualified teacher, and not
an authority on tajwīd.
