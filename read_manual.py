import pdfplumber, pathlib
pdf = pathlib.Path(r'C:\Users\Asher\Desktop\手册.pdf')
print('=== MANUAL PDF ===')
with pdfplumber.open(pdf) as doc:
    for i,page in enumerate(doc.pages[:10]):
        txt = page.extract_text()
        print(f'--- Page {i+1} ---')
        print(txt[:4000] if txt else '[no text]')
