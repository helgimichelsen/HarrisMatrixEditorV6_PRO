Harris Matrix Editor 6.0 PRO

Denne version er bygget efter at have testet de to faktiske .hmcx-filer:
- Á Sandum 2026 Harris Matrix(1).hmcx
- Á Sondum F8=F29(1).hmcx

V6 kan læse HMCX-filer som ZIP-arkiver med project.xml og matrix.xml/GraphML.
Den parser HMC's hmcnode- og hmcedge-data korrekt, inkl. type, layer, x/y, valid og relationstype.

Hovedfunktioner:
- Åbn ægte Harris Matrix Composer .hmcx-filer.
- Bevar originalt HMC-layout ved åbning.
- Auto-layout efter Harris-sekvens.
- Drag-and-drop af units.
- Zoom med musehjul, Fit view og pan med midter-/højreklik.
- Inspector-panel til ID, label, type, description, x/y osv.
- Relations-panel.
- Validity check med advarsler for manglende relationer/cycles.
- Clean lines fjerner transitive/redundante relationer.
- Eksport til HMCX, JSON, SVG og PDF.
- Windows EXE via GitHub Actions.

GitHub Actions workflow:
.github/workflows/build-editor-v6-pro.yml

Build:
Actions > Build Harris Matrix Editor V6 PRO EXE > Run workflow
Download artifact: HarrisMatrixEditorV6PRO-Windows-EXE
