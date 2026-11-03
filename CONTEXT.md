# Financial Research Assistant

A command-line agent that answers questions about Apple Inc. from its annual 10-K filing, supplemented by web search. This glossary fixes the words used for the parts of the filing and for what the assistant returns.

## Language

### The filing

**Filing**:
The single Apple 10-K the assistant answers from.
_Avoid_: document, report

**Item**:
A top-level part of the 10-K, such as Item 1A Risk Factors, Item 7 MD&A or Item 8 Financial Statements.
_Avoid_: chapter

**Section Path**:
The heading trail that locates text inside the Filing, such as `Item 7 > Gross Margin`.
_Avoid_: breadcrumb, location

### Retrieval

**Passage**:
A returnable unit of the Filing: one subsection, one risk factor, one note, or one table.
_Avoid_: chunk, parent, document

**Index Entry**:
An embedded excerpt of at most 350 tokens that points to its Passage.
_Avoid_: child chunk

**Table Card**:
The Index Entry for a table: its caption, column headers and row labels, with no figures.

### Answers

**Citation**:
The Section Path and page of a Passage, or the URL and date of a web result.
