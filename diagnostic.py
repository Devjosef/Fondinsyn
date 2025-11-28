from lxml import etree
import glob

# Find the first XML file
xml_files = glob.glob('**/*.xml', recursive=True)
if not xml_files:
    print("No XML files found.")
    exit(1)

test_file = xml_files[0]
print(f"Testing: {test_file}")

# Parse the XML using the etree library
tree = etree.parse(test_file)
root = tree.getroot()

# Show the structure 
print("\nNamespaces:", root.nsmap)
print("Root tag:", root.tag)
print("\nUnique tags:", sorted(set(elem.tag for elem in root.iter())))


# Test the namespace (update if needed from nsmap above this code)
ns = {'fi': 'http://schemas.fi.se/publika/vardepappersfonder/20200331'}

print("\nXPath tests:")
for path, name in [
    ('.//fi:Fondbolag_namn/text()', 'Fondbolag_namn'),
    ('.//fi:Fond_namn/text()', 'Fond_namn')
]:
    result = root.xpath(path, namespaces=ns)
    if result:
        print(f"{name}: {result}")
    else:
        print(f"{name}: Not found - check tag name or namespace")


csv_exists = len(glob.glob('swedish_funds_complete.csv')) > 0
print(f"\nCSV exists: {csv_exists}")
