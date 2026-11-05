# DocSuite – Android document viewer

View PDF, Word (.docx), Excel (.xlsx/.xls/.ods/.csv), PowerPoint (.pptx), images, text/code,
Markdown, HTML, audio, video and ZIP files on your phone. Everything is rendered on the device
and works offline.

## Get the APK
Every push to `main` builds the app on GitHub Actions and publishes **DocSuite.apk** under
**Releases**. Open the latest release on your phone, download `DocSuite.apk`, and install it.

## Features
- Open files from the app, or use **Open with → DocSuite** / **Share → DocSuite** from any app
  (File Manager, WhatsApp, Gmail, Drive…)
- PDF: zoom, jump to page, reader mode with search
- Spreadsheets: sheet tabs, filter, header row, copy as CSV
- Slides: text, images, tables, speaker notes
- Android back button closes the open document

## Project layout
- `app/src/main/assets/index.html` – the viewer (HTML/JS)
- `app/src/main/java/.../MainActivity.java` – WebView shell, file picker, "Open with" handling
- `.github/workflows/build-apk.yml` – builds and releases the APK

The signing key (`app/docsuite.keystore`, password `docsuite`) is kept in the repo so each new
build installs as an update. Replace it with your own private key before publishing on Play Store.
