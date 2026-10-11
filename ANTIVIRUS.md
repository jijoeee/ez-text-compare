# Antivirus false positives — the playbook

Every tool built with PyInstaller gets flagged by some antivirus engines. This is not a
bug in EZ Text Compare and it cannot be fixed by changing the app's code. This file
explains why, what to ignore, and what actually fixes it.

## Why it happens

PyInstaller wraps a Python program inside a small C launcher (the "bootloader") that
unpacks and runs the code. Real malware authors use the exact same tool, because it is
free and hides code well. Antivirus machine-learning models therefore learn that
"PyInstaller bootloader + compressed payload" is a risk pattern, and they flag it
regardless of what the program does.

Labels ending in `!ml` (for example `Trojan:Win32/Wacatac.B!ml`) are machine-learning
guesses, not matches against known malware. `Wacatac` and `Win32.Agent` are generic
buckets, roughly meaning "this looks packed".

## Step 1 — Decide whether it matters

Scan the **installer** (`EZ-Text-Compare-Setup-<version>.exe`) on
https://www.virustotal.com — not a zip of the `dist` folder, which inflates detections.

| What you see | What to do |
|---|---|
| 0 detections | Publish. |
| 1–3 detections, Microsoft Defender clean | Normal for an unsigned build. Publish, with an honest install note. |
| Only small engines: VBA32, Antiy-AVL, Jiangmin, MaxSecure, SecureAge, Bkav, Cylance | False positive. These have poor false-positive records. Submit them (step 2) but do not delay the release. |
| **Microsoft Defender flags it** | Act now. This is what almost every user runs. Do step 2 immediately and consider steps 3 and 4. |
| Kaspersky, ESET, Bitdefender, Avast/AVG, Sophos flag it | Act. Submit to each, and do step 3. |
| More than about 5 engines | Stop and investigate properly before publishing. |

## Step 2 — Submit the false positive (free, do this every release)

This is the highest-value action and costs nothing. Microsoft usually responds within
a few days, and once cleared, the fix applies to every Defender user worldwide.

- **Microsoft:** https://www.microsoft.com/en-us/wdsi/filesubmission
  Choose "Software developer", submit the installer, and state that it is a
  PyInstaller-packaged offline text compare utility, free and MIT-licensed.
- **Other vendors:** each VirusTotal result links to that vendor's false-positive form.
  Only bother with engines that actually matter (the list above).

Keep a record of submissions and outcomes in the log at the bottom of this file.

## Step 3 — Rebuild the PyInstaller bootloader (free, effective, one-off effort)

The flagged pattern is the *prebuilt* bootloader binary that ships with PyInstaller —
the identical bytes appear in thousands of files, including real malware. Compiling
your own produces a unique binary that most engines no longer recognise. This is the
single most effective free fix short of code signing.

You need the free **Visual Studio Build Tools** with the "Desktop development with C++"
workload. Then, in the project's virtual environment:

```bat
pip uninstall -y pyinstaller
git clone https://github.com/pyinstaller/pyinstaller.git
cd pyinstaller\bootloader
python ./waf all --target-arch=64bit
cd ..
pip install .
cd ..
rmdir /s /q pyinstaller
```

Then run `build.bat` again and rescan. Note this replaces the pinned PyInstaller from
`requirements-dev.txt`, so record which commit you built from.

## Step 4 — Code signing (the real, permanent fix)

A signed executable builds reputation with Microsoft SmartScreen and antivirus vendors
over time, and eventually stops being flagged at all. Unsigned files start from zero
every single release.

`build.py` already supports signing. Set one environment variable and it signs both
the app and the installer automatically:

```bat
set EZKERJA_SIGN_CMD=signtool sign /fd SHA256 /tr http://timestamp.digicert.com /td SHA256 /a "{file}"
```

Also uncomment `SignTool=signtool` and `SignedUninstaller=yes` in
`installer\installer.iss` so the uninstaller is signed too.

Ways to get a certificate, cheapest first:

1. **SignPath Foundation — free for open-source projects.**
   https://signpath.org · Provides an OV-level certificate from a trusted CA, with the
   private key held in their HSM. Requirements include an OSI-approved licence, a public
   repository, no proprietary components, visibly active development, two-factor
   authentication on the repository, and a credit line plus a signing-policy statement
   on the download page. EZ Text Compare is MIT-licensed, but its source is not
   public yet, so it does **not** qualify until the code is published on GitHub.
2. **Azure Trusted Signing** — around USD 10 per month. Public trust is limited to
   organisations in the US, Canada, EU and UK, and individual developers in the US and
   Canada, so a Malaysian entity may not currently be eligible. Check before paying.
3. **A commercial OV certificate** — roughly USD 200–400 per year, requires business
   verification and usually a hardware token or cloud HSM. This is the fallback for a
   paid product that cannot use the OSS programme.

## What NOT to do

- **Never tell a customer to disable their antivirus.** It destroys trust and is
  genuinely dangerous advice.
- **Do not use UPX compression** (`--noupx` is already set). It significantly increases
  detections.
- **Do not use `--onefile`.** It unpacks to a temporary folder at every launch, which
  looks like malware behaviour and is flagged more often. This project uses `--onedir`.
- **Do not hide the problem.** Publish the VirusTotal link and an honest note. Being
  upfront reads as competence.

## Note for the download page

> **Windows may show a warning.** EZ Text Compare is new and not yet code signed, so
> Windows SmartScreen may say "Windows protected your PC". Click **More info**, then
> **Run anyway**. You can verify the download yourself: the SHA-256 checksum and the
> full VirusTotal scan are published above.

## Submission log

| Date | Version | Detections | Vendors | Submitted | Outcome |
|---|---|---|---|---|---|
| | 1.0.0 | | | | |
