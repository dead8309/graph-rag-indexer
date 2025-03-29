# grag indexer

mostly an experiment to see how fast I can index a large number of files and search them using graph rag and graph database and compare it to a traditional rag

# todo

parser - TODO: recheck this condition, we might also need small functions for indexing purposes they could help in rag maybe
parser - NOTE: maybe dynamic imports?, will have to check later
models - TODO: i'll have to rethink about this, requires can be also called inside functions (lazy loading)
parser- NOTE: for now we don't filter out small functions

# results

```sh
--- Performing Vector Search ---
Query: 'create a new product'
initializing vector store
Searching snippets in vector store with query: create a new product
Search returned 3 results.

Top Vector Search Results:

- id: controllers/product.controller.js::createProduct (score: 0.5976)
- id: controllers/product.controller.js::updateProduct (score: 0.4588)
- id: controllers/product.controller.js::deleteProduct (score: 0.4443)

  RAG IDs found: ['controllers/product.controller.js::createProduct', 'controllers/product.controller.js::updateProduct', 'controllers/product.controller.js::deleteProduct']
```
