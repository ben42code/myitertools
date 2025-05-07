import os
import sys

print(">>>>>>>>>>>>>>>>> Extending PYTHONPATH <<<<<<<<<<<<<<<<<<")
for newEntry in [
    "src",          # dependency on main projects located in src
]:
    sys.path.append(os.path.join(os.getcwd(), newEntry))
    print(f'''+"{sys.path[-1]}"''')
print(">>>>>>>>>>>>>>>>>>>>>>>>>>>><<<<<<<<<<<<<<<<<<<<<<<<<<<<<")
