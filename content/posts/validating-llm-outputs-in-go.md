---
title: "Validating LLM Outputs in Go"
date: 2026-01-12T14:00:00+05:30
description: A complete guide to validating structured LLM outputs using godantic - Pydantic for Go
tags:
  - go
  - LLM
  - validation
  - godantic
  - openai
  - structured output
---

---

## The Problem

LLMs hallucinate. They return wrong types, invalid values, and malformed data. A rating meant to be 1-5 comes back as 10. An email field contains "not provided". A required field is missing entirely.

In Python, [Pydantic](https://docs.pydantic.dev/) is the standard solution - define a model, validate the output, catch errors before they crash your app. But what about Go?

[godantic](https://github.com/deepankarm/godantic) brings Pydantic-style validation to Go. Full JSON schema generation for LLM APIs. This post shows common patterns for validating LLM outputs in Go.

---

## Basic Validation

Define a struct and add `Field{Name}()` methods to specify constraints:

```go
type ContactInfo struct {
    Name    string  `json:"name"`
    Email   string  `json:"email"`
    Phone   string  `json:"phone"`
    Company *string `json:"company,omitempty"`
}

func (c *ContactInfo) FieldName() godantic.FieldOptions[string] {
    return godantic.Field(
        godantic.Required[string](),
        godantic.MinLen(1),
        godantic.Description[string]("Contact's full name"),
    )
}

func (c *ContactInfo) FieldEmail() godantic.FieldOptions[string] {
    return godantic.Field(
        godantic.Required[string](),
        godantic.Email(),  // Built-in email validation
        godantic.Description[string]("Contact's email address"),
    )
}
```

Validate LLM output:

```go
validator := godantic.NewValidator[ContactInfo]()
contact, errs := validator.Unmarshal([]byte(llmResponse))

if len(errs) > 0 {
    for _, e := range errs {
        fmt.Printf("%v: %s\n", e.Loc, e.Message)
        // [Email]: value does not match pattern ^[a-zA-Z0-9._%+-]+@...
    }
}
```

---

## Numeric Constraints

Constrain numeric values with `Min`, `Max`, `ExclusiveMin`, `ExclusiveMax`:

```go
type ProductReview struct {
    ProductName string   `json:"product_name"`
    Rating      int      `json:"rating"`
    Pros        []string `json:"pros"`
    Cons        []string `json:"cons"`
    Summary     string   `json:"summary"`
}

func (p *ProductReview) FieldRating() godantic.FieldOptions[int] {
    return godantic.Field(
        godantic.Required[int](),
        godantic.Min(1),
        godantic.Max(5),
        godantic.Description[int]("Rating from 1 (worst) to 5 (best)"),
    )
}

func (p *ProductReview) FieldPros() godantic.FieldOptions[[]string] {
    return godantic.Field(
        godantic.Required[[]string](),
        godantic.MinItems[string](1),  // At least one pro
        godantic.Description[[]string]("List of positive aspects"),
    )
}
```

When the LLM returns `"rating": 10`:

```
[Rating]: value must be <= 5
```

---

## Custom Validators

Add custom validation logic with `godantic.Validate()`:

```go
func (c *ContactInfo) FieldPhone() godantic.FieldOptions[string] {
    return godantic.Field(
        godantic.Required[string](),
        godantic.Validate(func(phone string) error {
            // Strip formatting: (555) 123-4567 -> 5551234567
            re := regexp.MustCompile(`\D`)
            digits := re.ReplaceAllString(phone, "")
            if len(digits) < 10 {
                return fmt.Errorf("phone must have at least 10 digits, got %d", len(digits))
            }
            return nil
        }),
    )
}
```

Output:

```
[Phone]: phone must have at least 10 digits, got 3
```

---

## Nested Models

Nested structs are validated automatically:

```go
type Specification struct {
    Name  string `json:"name"`
    Value string `json:"value"`
}

type Review struct {
    ReviewerName string `json:"reviewer_name"`
    Rating       int    `json:"rating"`
    Comment      string `json:"comment"`
}

type Product struct {
    Name           string          `json:"name"`
    Price          float64         `json:"price"`
    Specifications []Specification `json:"specifications"`
    Reviews        []Review        `json:"reviews"`
}

func (r *Review) FieldRating() godantic.FieldOptions[int] {
    return godantic.Field(
        godantic.Required[int](),
        godantic.Min(1),
        godantic.Max(5),
    )
}
```

If a nested review has an invalid rating:

```
[Reviews [0] Rating]: value must be <= 5
```

---

## Schema Generation for LLM APIs

Generate JSON schemas for OpenAI, Gemini, or Anthropic structured outputs:

```go
schemaGen := schema.NewGenerator[ProductReview]()
flatSchema, err := schemaGen.GenerateFlattened()
```

Output:

```json
{
  "type": "object",
  "properties": {
    "rating": {
      "type": "integer",
      "minimum": 1,
      "maximum": 5,
      "description": "Rating from 1 (worst) to 5 (best)"
    },
    "pros": {
      "type": "array",
      "items": {"type": "string"},
      "minItems": 1,
      "description": "List of positive aspects"
    }
  },
  "required": ["product_name", "rating", "pros", "cons", "summary"]
}
```

The same struct definition drives both validation and schema generation.

---

## OpenAI Structured Outputs

Use the generated schema with OpenAI's structured output API:

```go
// Generate schema
schemaGen := schema.NewGenerator[BookSummary]()
flatSchema, err := schemaGen.GenerateFlattened()

// Call OpenAI with structured output
completion, _ := client.Chat.Completions.New(ctx, openai.ChatCompletionNewParams{
    Messages: []openai.ChatCompletionMessageParamUnion{
        openai.SystemMessage("Extract structured book information."),
        openai.UserMessage(bookDescription),
    },
    Model: openai.ChatModelGPT4o2024_08_06,
    ResponseFormat: openai.ChatCompletionNewParamsResponseFormatUnion{
        OfJSONSchema: &openai.ResponseFormatJSONSchemaParam{
            JSONSchema: openai.ResponseFormatJSONSchemaJSONSchemaParam{
                Name:   "book_summary",
                Schema: flatSchema,
                Strict: openai.Bool(true),
            },
        },
    },
})

// Validate the response (even with strict mode, validate anyway)
validator := godantic.NewValidator[BookSummary]()
book, errs := validator.Unmarshal([]byte(completion.Choices[0].Message.Content))
if len(errs) > 0 {
    // Handle validation errors
}
```

---

## Pydantic to Godantic Cheatsheet

| Pydantic | Godantic |
|----------|----------|
| `class Model(BaseModel)` | `type Model struct` + `godantic.NewValidator[Model]()` |
| `@field_validator` | `godantic.Validate(func)` |
| `Field(ge=1, le=5)` | `godantic.Min(1), godantic.Max(5)` |
| `Field(min_length=1)` | `godantic.MinLen(1)` |
| `EmailStr` | `godantic.Email()` |
| `Optional[T] = None` | `*T` (pointer) |
| `Field(default=...)` | `godantic.Default[T](value)` |
| `List[T]` with `min_items` | `godantic.MinItems[T](n)` |
| `model.model_json_schema()` | `schema.NewGenerator[T]().GenerateFlattened()` |

---

## Streaming Partial JSON

For parsing incomplete JSON as it streams from LLMs, see [Streaming Partial JSON from LLMs in Go](/posts/streaming-partial-json-llm/).

---

## Try It

```bash
go get github.com/deepankarm/godantic
```

Working examples:
- [OpenAI Structured Output](https://github.com/deepankarm/godantic/tree/main/examples/openai-structured-output)
- [Gemini Structured Output](https://github.com/deepankarm/godantic/tree/main/examples/gemini-structured-output)

---
