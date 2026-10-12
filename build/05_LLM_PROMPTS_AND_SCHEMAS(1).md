# 05 — Every LLM instruction string, prompt format and JSON schema (verbatim, generated from the working code)

These are exact. They are also present inside the appendix source files; they are repeated here so you can see all LLM-facing text in one place.
**Do not edit them casually** — the tests and the measured accuracy depend on their wording (e.g. the classifier's rule about when to ask for clarification removed four unnecessary questions; not sending the file name to the extractor prevents answer leakage).

### 5.1 Receipt extraction — `extraction.INSTRUCTIONS` (agent output_type = `Receipt`, retries=2)

```text
You extract structured data from a photo or scan of an expense receipt.
- Read only what is printed. Never invent a value; use null when a field is absent.
- Dates on these receipts are day-first (DD/MM/YYYY). Output ISO YYYY-MM-DD.
- "Rs" or the rupee sign means INR. total is the final amount paid including tax.
- `category` is only a short free-text description of the kind of expense (for example
  "restaurant meal" or "petrol"); do not try to match any policy.
- Give honest per-field confidence: lower it for blur, glare, folds, or partial text.
- If the image is not a receipt or is unreadable, set readable=false.
```

User message to the extraction agent: a list `[text, BinaryContent(JPEG page 1), BinaryContent(page 2) ...]` where text is exactly `Extract the receipt in the attached image(s).` and, for PDFs with embedded text, `\n\nText embedded in the PDF (may be incomplete):\n<text>` is appended. The file name is never included.

### 5.2 Policy interpretation — `interpreter.INSTRUCTIONS` (output_type = `PolicyConstraints`, retries=3, with output validator)

```text
You convert a corporate reimbursement policy document into structured constraints.
Rules:
- Use only what the document says. Never invent a limit, grade, or category.
- Every item must cite its clause number and a verbatim `quote` from that clause. A limit's
  amount must appear in its quote.
- Define a category for each kind of expense the document makes reimbursable or excludes. Use short
  lowercase snake_case ids. Reuse the ids you are given from other documents instead of creating
  near-duplicates.
- Expand grade bands (for example "Manager grades") into individual grade codes using the
  document's own definitions. If the document does not define the codes, leave grades empty.
- Choose `unit` from the wording: "per night", "per receipt", "per day", "per month".
- over_limit_action: "partial" if the document says the amount up to the limit is reimbursed;
  "needs_approval" if above the limit only with a manager exception; otherwise "reject".
- Put things the policy says are never reimbursable under `exclusions`, with a category for them.
- Do not output an item for clauses that contain no constraint.
```

### Example interpreter user prompt (second document; header + document text)

```text
Document file name: grade_entitlements.md
Category ids already defined by other documents (reuse them): <comma-separated ids, sorted>

--- DOCUMENT ---
<entire markdown text of the document>
```

Validator retry message sent back to the model when grounding fails: `Fix these problems and return the full result again:\n- <problem 1>\n- <problem 2> ...`.

### 5.3 Classification — `classifier.INSTRUCTIONS` (output_type = `Classification`, retries=2, validator: category must be a policy category id)

```text
You classify one expense into a reimbursement category defined by the company's policy.
- Choose from the listed category ids only. Judge by what was actually bought (line items,
  vendor type), not by how the employee might want to claim it.
- Prefer a category the employee is eligible for when it genuinely fits; if the expense only fits a
  category that is excluded or unavailable to their grade, still choose that category so the
  policy can explain the outcome.
- Give a one or two sentence `reasoning` an employee can read.
- Set needs_clarification=true ONLY when the choice between categories would change what is
  reimbursed (different eligibility or limits) and the bill itself does not settle it, or when you
  cannot tell what was bought. Then pick the most likely category and ask one short question.
- Never ask about things collected elsewhere: the business purpose, the date, the amount, or taxes
  (a total above the sum of line items is normal tax), and never ask just to confirm an obvious category.
```

### Example classifier user prompt (real, for the hotel receipt, employee M2, policy as interpreted)

```text
Employee: grade M2, role Sales Manager, base city Pune

Policy categories:
- meals: Meals. Meal expenses [available to grade M2]
- local_transport: Local transport. Local transport expenses [available to grade M2]
- fuel: Fuel. Fuel expenses [available to grade M2]
- communication: Communication. Mobile and broadband bills [available to grade M2]
- office_supplies: Office supplies. Office supplies expenses [available to grade M2]
- training: Training. Training expenses [available to grade M2]
- lodging: Lodging. Lodging expenses [available to grade M2]
- client_entertainment: Client entertainment. Client entertainment expenses [available to grade M2]
- personal_expenses: Personal expenses. Personal expenses, medical expenses, fines and penalties [never reimbursable]

Expense:
- vendor: LOTUS GROVE HOTEL
- date: 2026-09-15
- total: 7168.0 INR
- line items: Room 1 night (5800.0); Breakfast (600.0)
- extractor's description: lodging
- nights: None
- notes: Subtotal 6400.00 + tax 768.00 = 7168.00, which matches the total. Receipt date is in the future relative to typical submission, so verify the date.
```

### 5.4 Chat agent — `chat.INSTRUCTIONS` (plus a dynamic line: `The employee is <name>, grade <g>, <role>, based in <city>.`)

```text
You are an expense reimbursement assistant helping an employee turn their receipts into a claim.
- Facts come from tools. Never guess amounts, statuses or policy. Call claim_status, explain_item or
  search_policy before answering questions about them.
- When the employee gives information that answers an open question or corrects a receipt, record it
  with record_answer, then say what changed and what (if anything) is still needed.
- When you explain a decision, mention the policy clause reference (like TEP-2.1) and the amounts
  from the tool output. Say plainly what is eligible and what is not.
- Ask for only what is missing. Do not submit the claim; the employee presses Submit when it is ready.
- Be brief: at most five short sentences. Plain text only: no markdown, no asterisks, no headings,
  no bullet lists. Mention only the receipts the question is about.
```

Chat tools (names, parameters, docstrings are in `chat.py`): `claim_status()`, `explain_item(receipt)`, `search_policy(query)`, `record_answer(kind, target, value)`.

## JSON schemas the LLM must satisfy (`Model.model_json_schema()`)

### 5.5 `Receipt` schema

```json
{
  "$defs": {
    "FieldConfidence": {
      "properties": {
        "vendor": {
          "description": "0-1 confidence the vendor name is correct",
          "maximum": 1,
          "minimum": 0,
          "title": "Vendor",
          "type": "number"
        },
        "date": {
          "description": "0-1 confidence the date is correct (0 if absent)",
          "maximum": 1,
          "minimum": 0,
          "title": "Date",
          "type": "number"
        },
        "total": {
          "description": "0-1 confidence the total is correct",
          "maximum": 1,
          "minimum": 0,
          "title": "Total",
          "type": "number"
        }
      },
      "required": [
        "vendor",
        "date",
        "total"
      ],
      "title": "FieldConfidence",
      "type": "object"
    },
    "LineItem": {
      "properties": {
        "description": {
          "title": "Description",
          "type": "string"
        },
        "amount": {
          "anyOf": [
            {
              "type": "number"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Amount"
        }
      },
      "required": [
        "description"
      ],
      "title": "LineItem",
      "type": "object"
    }
  },
  "properties": {
    "readable": {
      "description": "False if the image is not a receipt or is unreadable",
      "title": "Readable",
      "type": "boolean"
    },
    "vendor": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "description": "Merchant name as printed",
      "title": "Vendor"
    },
    "receipt_date": {
      "anyOf": [
        {
          "format": "date",
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "description": "Date on the receipt as ISO YYYY-MM-DD. Printed dates are day-first (DD/MM/YYYY). Null if no date is visible; never guess.",
      "title": "Receipt Date"
    },
    "total": {
      "anyOf": [
        {
          "type": "number"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "description": "Final amount paid, including tax",
      "title": "Total"
    },
    "tax": {
      "anyOf": [
        {
          "type": "number"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "description": "Total tax amount, null if not shown",
      "title": "Tax"
    },
    "currency": {
      "description": "ISO 4217 code, e.g. INR, USD, SGD. Rs means INR.",
      "title": "Currency",
      "type": "string"
    },
    "category": {
      "description": "Short free-text description of the kind of expense, e.g. 'restaurant meal', 'taxi ride', 'hotel stay', 'petrol'. This is only a hint; policy categories are assigned later.",
      "title": "Category",
      "type": "string"
    },
    "nights": {
      "anyOf": [
        {
          "type": "integer"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "description": "Number of nights for a hotel stay, otherwise null",
      "title": "Nights"
    },
    "line_items": {
      "items": {
        "$ref": "#/$defs/LineItem"
      },
      "title": "Line Items",
      "type": "array"
    },
    "receipt_number": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "description": "Bill / invoice number if printed",
      "title": "Receipt Number"
    },
    "payment_method": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "description": "e.g. CARD, CASH, UPI, if shown",
      "title": "Payment Method"
    },
    "confidence": {
      "$ref": "#/$defs/FieldConfidence"
    },
    "notes": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "description": "Anything unusual worth a human's attention",
      "title": "Notes"
    }
  },
  "required": [
    "readable",
    "currency",
    "category",
    "confidence"
  ],
  "title": "Receipt",
  "type": "object"
}
```

### 5.6 `PolicyConstraints` schema

```json
{
  "$defs": {
    "AgeRule": {
      "properties": {
        "clause": {
          "description": "clause number exactly as printed in the document, e.g. '2.1'",
          "title": "Clause",
          "type": "string"
        },
        "quote": {
          "description": "the words from that clause that support this item, copied verbatim",
          "title": "Quote",
          "type": "string"
        },
        "document": {
          "default": "",
          "description": "leave empty; filled in by the system",
          "title": "Document",
          "type": "string"
        },
        "max_age_days": {
          "description": "maximum age of a receipt, in days",
          "title": "Max Age Days",
          "type": "integer"
        }
      },
      "required": [
        "clause",
        "quote",
        "max_age_days"
      ],
      "title": "AgeRule",
      "type": "object"
    },
    "CategoryDef": {
      "properties": {
        "id": {
          "description": "short lowercase snake_case id, e.g. 'meals' or 'lodging'",
          "title": "Id",
          "type": "string"
        },
        "label": {
          "description": "human-readable name",
          "title": "Label",
          "type": "string"
        },
        "description": {
          "description": "what kinds of expenses belong in this category, per the policy",
          "title": "Description",
          "type": "string"
        }
      },
      "required": [
        "id",
        "label",
        "description"
      ],
      "title": "CategoryDef",
      "type": "object"
    },
    "Entitlement": {
      "properties": {
        "clause": {
          "description": "clause number exactly as printed in the document, e.g. '2.1'",
          "title": "Clause",
          "type": "string"
        },
        "quote": {
          "description": "the words from that clause that support this item, copied verbatim",
          "title": "Quote",
          "type": "string"
        },
        "document": {
          "default": "",
          "description": "leave empty; filled in by the system",
          "title": "Document",
          "type": "string"
        },
        "category": {
          "description": "id of a category defined in `categories`",
          "title": "Category",
          "type": "string"
        },
        "grades": {
          "description": "every grade code allowed to claim the category, with grade bands expanded to individual codes using the document's own definitions",
          "items": {
            "type": "string"
          },
          "title": "Grades",
          "type": "array"
        }
      },
      "required": [
        "clause",
        "quote",
        "category",
        "grades"
      ],
      "title": "Entitlement",
      "type": "object"
    },
    "Exclusion": {
      "properties": {
        "clause": {
          "description": "clause number exactly as printed in the document, e.g. '2.1'",
          "title": "Clause",
          "type": "string"
        },
        "quote": {
          "description": "the words from that clause that support this item, copied verbatim",
          "title": "Quote",
          "type": "string"
        },
        "document": {
          "default": "",
          "description": "leave empty; filled in by the system",
          "title": "Document",
          "type": "string"
        },
        "category": {
          "title": "Category",
          "type": "string"
        },
        "reason": {
          "title": "Reason",
          "type": "string"
        }
      },
      "required": [
        "clause",
        "quote",
        "category",
        "reason"
      ],
      "title": "Exclusion",
      "type": "object"
    },
    "Limit": {
      "properties": {
        "clause": {
          "description": "clause number exactly as printed in the document, e.g. '2.1'",
          "title": "Clause",
          "type": "string"
        },
        "quote": {
          "description": "the words from that clause that support this item, copied verbatim",
          "title": "Quote",
          "type": "string"
        },
        "document": {
          "default": "",
          "description": "leave empty; filled in by the system",
          "title": "Document",
          "type": "string"
        },
        "category": {
          "title": "Category",
          "type": "string"
        },
        "amount": {
          "title": "Amount",
          "type": "number"
        },
        "currency": {
          "default": "INR",
          "description": "ISO 4217 code",
          "title": "Currency",
          "type": "string"
        },
        "unit": {
          "enum": [
            "per_receipt",
            "per_night",
            "per_day",
            "per_month"
          ],
          "title": "Unit",
          "type": "string"
        },
        "grades": {
          "anyOf": [
            {
              "items": {
                "type": "string"
              },
              "type": "array"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "description": "grade codes this limit applies to, or null when it applies to all grades",
          "title": "Grades"
        },
        "over_limit_action": {
          "description": "partial: the policy reimburses up to the limit; needs_approval: above the limit only with a manager exception; reject: above the limit is not reimbursed",
          "enum": [
            "partial",
            "needs_approval",
            "reject"
          ],
          "title": "Over Limit Action",
          "type": "string"
        },
        "requires_approval": {
          "default": false,
          "description": "true if the policy requires prior approval even when under the limit",
          "title": "Requires Approval",
          "type": "boolean"
        }
      },
      "required": [
        "clause",
        "quote",
        "category",
        "amount",
        "unit",
        "over_limit_action"
      ],
      "title": "Limit",
      "type": "object"
    }
  },
  "properties": {
    "categories": {
      "items": {
        "$ref": "#/$defs/CategoryDef"
      },
      "title": "Categories",
      "type": "array"
    },
    "entitlements": {
      "items": {
        "$ref": "#/$defs/Entitlement"
      },
      "title": "Entitlements",
      "type": "array"
    },
    "limits": {
      "items": {
        "$ref": "#/$defs/Limit"
      },
      "title": "Limits",
      "type": "array"
    },
    "exclusions": {
      "items": {
        "$ref": "#/$defs/Exclusion"
      },
      "title": "Exclusions",
      "type": "array"
    },
    "age_rules": {
      "items": {
        "$ref": "#/$defs/AgeRule"
      },
      "title": "Age Rules",
      "type": "array"
    }
  },
  "title": "PolicyConstraints",
  "type": "object"
}
```

### 5.7 `Classification` schema

```json
{
  "properties": {
    "category": {
      "description": "id of one listed policy category",
      "title": "Category",
      "type": "string"
    },
    "reasoning": {
      "description": "why this category fits this expense",
      "title": "Reasoning",
      "type": "string"
    },
    "confidence": {
      "maximum": 1,
      "minimum": 0,
      "title": "Confidence",
      "type": "number"
    },
    "needs_clarification": {
      "default": false,
      "title": "Needs Clarification",
      "type": "boolean"
    },
    "clarification_question": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "title": "Clarification Question"
    }
  },
  "required": [
    "category",
    "reasoning",
    "confidence"
  ],
  "title": "Classification",
  "type": "object"
}
```

