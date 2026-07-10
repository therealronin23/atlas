# Domain Model Importer

Atlas must inspect databases, folders, exports and documents to infer domain models.

It must ask concrete confirmation questions when unsure.

Example:

```text
This table `mov_cli` looks like clients. Is that correct?
This field `nif` looks like a tax ID. Treat as sensitive?
```
