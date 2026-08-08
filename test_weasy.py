from weasyprint import HTML
html = """
<html>
<style>
@page {
    margin-top: 50mm;
    background-color: #ffcccc;
}
body { background-color: #ccccff; height: 300mm; }
</style>
<body><h1>Hello World</h1></body>
</html>
"""
HTML(string=html).write_pdf("test_margin.pdf")
print("Done")
