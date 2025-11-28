from lxml import etree
import glob

xml_files = glob.glob('**/*.xml', recursive=True)
test_file = xml_files[0]
print(f"Testing: {test_file}")

tree = etree.parse(test_file)
root = tree.getroot()
ns = {'fi': 'http://schemas.fi.se/publika/vardepappersfonder/20200331'}

print("\nFUND INFO:")
print("Fondbolag_namn:", root.xpath('.//fi:Fondbolag_namn/text()', namespaces=ns))
print("Fond_namn:", root.xpath('.//fi:Fond_namn/text()', namespaces=ns))

print("\nHOLDINGS PATHS (counts):")
paths = [
    './/fi:FinansielltInstrument',
    './/fi:Instrument', 
    './/fi:Holding',
    './/fi:Position',
    './/FinansielltInstrument',
    './/*[contains(name(), "Instrument")]',
    './/*[contains(name(), "Holding")]'
]

for path in paths:
    ns_use = ns if 'fi:' in path else None
    count = len(root.xpath(path, namespaces=ns_use))
    print(f"  {path}: {count}")

# Best path (highest count of nodes)
best_path = max(paths, key=lambda p: len(root.xpath(p, namespaces=ns if 'fi:' in p else None)))
holdings = root.xpath(best_path, namespaces=ns if 'fi:' in best_path else None)

print(f"\nFIRST HOLDING ({best_path}):")
if holdings:
    first = holdings[0]
    print("  Tags in first holding:")
    for child in first.iter():
        text = child.text[:50] if child.text else ""
        print(f"    {child.tag}: {text}")
