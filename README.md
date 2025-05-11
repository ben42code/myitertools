# ben42code.myitertools
Providing some additional capabilities on top of itertools.

## Example for `ben42code.myitertools.islice_extended`
`islice_extended` does support negative start/stop indexes and negative step.

```python
from ben42code.myitertools import islice_extended

input = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]
result = list(islice_extended(input, -1, -5, -1))
print(f"Result: {result}")

exit()
```
Ouput:
```
Result: [9, 8, 7, 6]
```