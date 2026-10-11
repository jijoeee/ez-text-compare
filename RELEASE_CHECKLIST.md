# Release checklist

Work through this for every public release. It takes about 30 minutes.

## 1. Version
- [ ] Bump `__version__` in `ezcompare/__init__.py` (the only place it's defined).
- [ ] Add an entry to `CHANGELOG.md`.

## 2. Build
- [ ] Inno Setup installed? Without it no installer is produced, only the app folder.
      Free from https://jrsoftware.org/isdl.php
- [ ] Double-click `build.bat`. Tests must pass or the build stops.
- [ ] Confirm `dist\EZ-Text-Compare-Setup-<version>.exe` exists. That single file is
      what you publish, not the `dist\EZ Text Compare\` folder.
- [ ] Confirm `dist\EZ-Text-Compare-<version>-portable.zip` exists (the no-install version).
- [ ] Note the SHA-256 checksums it prints.

## 3. Test on a clean Windows (no Python installed)
Windows Sandbox is free on Windows 10/11 Pro. Turn it on once via
"Turn Windows features on or off" > Windows Sandbox.

- [ ] Double-click `dist\sandbox-test.wsb`. The release folder opens inside the sandbox.
- [ ] Run the installer. No admin prompt should appear.
- [ ] Check the Start menu icon, taskbar icon and title-bar icon all show the EZKerja logo.
- [ ] Right-click the .exe > Properties > Details: publisher and version are filled in.
- [ ] Drag two files from Explorer onto the window at once: the older one lands on the left.
- [ ] Drag one file onto the right pane: it replaces only the right side.
- [ ] Compare two real configs (before/after a change) and two real logs. Check a changed
      line shows only the changed characters highlighted, and clicking it shows its partner.
- [ ] Untick "Ignore line order": the side-by-side view lines up, both sides scroll
      together, a moved line is shown as moved.
- [ ] Tick "Dates and times" on two logs: timestamp-only differences disappear.
- [ ] Type a broken pattern such as  ([a-z  : a clear message, no crash.
- [ ] Open a binary file (an .exe or .zip): refused with a clear message.
- [ ] Open a UTF-16 file (PowerShell `Out-File` output) and a Windows-1252 file: text reads
      correctly.
- [ ] Two 20,000-line logs where every line differs: the window stays responsive, Stop works,
      the result says pairing was limited.
- [ ] Paste text from the clipboard on one side and compare with a file.
- [ ] Export to Excel and open it: both sheets, colours, Malay text and symbols not garbled.
- [ ] F3 / Shift+F3 and Alt+Up / Alt+Down move between differences.
- [ ] At 125% and 150% display scaling, both text panes are sharp, line numbers line up
      with their lines, and nothing in the toolbar is clipped.
- [ ] Switch light/dark mode.
- [ ] Uninstall from Settings > Apps. Nothing should be left in Program Files.

If Windows Sandbox isn't available, use a spare PC or a free Windows VM (VirtualBox).

## 4. Antivirus and SmartScreen

**Scan the installer, not a zip of the folder.** A zip of `dist\EZ Text Compare\`
makes scanners inspect dozens of loose DLLs out of context and inflates detections.
The installer is also what customers actually download.

- [ ] Upload the installer to https://www.virustotal.com and save the report link.
- [ ] Confirm the tags show `contains-pe` only. If `contains-elf` or `contains-macho`
      appears, another platform's binaries leaked in; check the filter in
      `ez_text_compare.spec`.
- [ ] Read the decision table in `ANTIVIRUS.md` and act on it. Short version:
      Defender clean and under about 3 small-engine hits is normal and publishable;
      Defender flagging it is a blocker.
- [ ] Submit any false positives (free): https://www.microsoft.com/en-us/wdsi/filesubmission
- [ ] Record the result in the submission log at the bottom of `ANTIVIRUS.md`.

## 5. Publish
- [ ] Upload the installer to the download location (keep a copy off the Orange Pi).
- [ ] Publish the SHA-256 checksum and VirusTotal link on the download page.
- [ ] Also upload the portable zip, with its own SHA-256.
