# CTSSB-1M
CTSSB-1M is a cleaned version of TSSB-3M and consists of nearly 1 million true single statement bug fixes (TSSB) mined from Python open source repositories. The intended use case for this dataset is to study what types of bugs developers introduce and how they fix them. Due to more precise selection methodology, it is possible to employ the dataset as a base for evaluating bug detection or automatic repair method.

Note that CTSSB-1M does not allow comodification. In other words, single statement commits contained in this dataset never modify other files in the same commit. Therefore, TSSB-1M is likely cleaner and is more likely to contain true bug fixes. Still, the employed selection process is performed heuristically. Employing this dataset for evaluation might require an additional filtering process. 

**Disclaimer:** All commits contained in this dataset come from publicly accessible open-source projects (mined in October 2021). Note that because of concerns regarding licensing issues we cannot include complete source code files. The original source code, however, can be obtained directly from the source projects.

## Dataset description
CTSSB-1M indexes nearly 1 million (966985 in total) single statement bug fixes coming from more than 168K git projects. All dataset entries are stored in a compressed [jsonlines](https://jsonlines.org) format. Because of size of the dataset, we sharded the dataset in files containing 100.000 commits each. Each entry does not only contain information to access the original source code but also information supporting basic analyses. A description of the stored json objects is given in the following:

**Commit details:**
- **project:** Name of the git project where the commit occurred.
- **project_url:** URL of project containing the commit
- **commit_sha:** commit SHA of the code change
- **parent_sha:** commit SHA of the parent commit
- **file_path:** File path of the changed source file
- **diff:** Universal diff describing the change made during the commit
- **before:** Python statement before commit
- **after:** Python statement after commit (addresses the same line)

**Commit analysis:**
- **likely_bug:** `true` if the commit message indicates that the commit is a bug fix. This is heuristically determined.
- **comodified:** `true` if the commit modifies more than one statement in a single file (formatting and comments are ignored).
- **in_function:** `true` if the changed statement appears inside a Python function
- **sstub_pattern:** the name of the single statement change pattern the commit can be classified for (if any). Default: `SINGLE_STMT`
- **edit_script:** A sequence of AST operation to transform the code before the commit to the code after the commit (includes `Insert`, `Update`, `Move` and `Delete` operations).

## Edit scripts
To give an example of the computed edit script, we provide an example for AST edit script computed for the given universal diff:

```diff
def to_internal_value(self, data):
     # TODO: remove when API v1 is removed
-   if 'credential_type' not in data:
+   if 'credential_type' not in data and self.version == 1:
         # If `credential_type` is not provided, assume the payload is a
         # v1 credential payload that specifies a `kind` and a flat list
         # of field values
```

**SStuB pattern:** `MORE_SPECIFIC_IF`

**Edit script:**
```
[
  Insert((boolean_operator, N0), (if_statement, line 3:9 - 3:42), 1),
  Move((comparison_operator, line 3:12 - 3:41), N0, 0),
  Insert(and:and, N0, 1),
  Insert((comparison_operator, N1), N0, 2),
  Insert((attribute, N2), N1, 0),
  Insert(==:==, N1, 1),
  Insert(integer:1, N1, 2),
  Insert(identifier:self, N2, 0),
  Insert(.:., N2, 1),
  Insert(identifier:version, N2, 2)
]
```
To get a better intuition for the edit script, we visualize the edit script in a more human readable format. The edit scripts stored in the dataset are stored in a machine readable Json format. 

Note that the edit script indexes existing AST nodes via code position, while newly introduced nodes a references via anonymous identifiers (N0, N1, N2, ...). Tokens are generally represented by its type and token string (token_type:token_str).


**Note:**
All edit scripts are computed based on custom differencing library [code_diff](https://github.com/cedricrupb/code_diff). The library combines the classical GumTree algorithm with a best-effort AST parser based on [tree-sitter](https://tree-sitter.github.io/tree-sitter/). In contrast to most standard AST parsers, tree-sitter maintains all code tokens in the computed abstract syntax tree, which is also reflected by the edit script (e.g. explicit inserts of parentheses or divider).