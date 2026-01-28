---
title: "Pydantic for Go: Validating LLM Outputs with godantic"
date: 2026-01-12T14:00:00+05:30
description: Schema generation and runtime validation for structured LLM outputs in Go, using godantic
tags:
  - go
  - LLM
  - validation
  - godantic
  - openai
  - structured output
---

## The Problem

LLMs hallucinate. They return wrong types, invalid values, and malformed data. A rating meant to be 1-5 comes back as 10. An email field contains "not provided". A required field is missing entirely.

In Python, [Pydantic](https://docs.pydantic.dev/) is the standard solution - define a model, validate the output, catch errors before they crash your app. But what about Go?

## Why Existing Go Libraries Don't Cut It

Go has validation libraries. It has JSON schema libraries. But none of them solve the LLM output problem end-to-end.

**Struct tag validators** like [`go-playground/validator`](https://github.com/go-playground/validator) handle runtime validation, but through string-based struct tags (`validate:"required,email,min=1"`). These are invisible to your IDE, impossible to unit test in isolation, and don't generate schemas. You validate *after* the fact but can't tell the LLM what shape to produce.

**JSON schema libraries** like [`invopop/jsonschema`](https://github.com/invopop/jsonschema) generate schemas from structs, but don't validate. You can describe what you want, but can't enforce it when the response arrives.

**The missing piece is unification.** Pydantic's power comes from one model definition that drives schema generation *and* validation *and* serialization. Define `Field(ge=1, le=5)` once - Pydantic generates the JSON schema for your LLM API call, then validates the response against the same constraints. In Go, you'd need to wire together separate libraries, keep constraints in sync manually, and handle LLM-specific schema quirks (like flattening `$ref`s for OpenAI) yourself.

**Go has no union types.** LLM responses are often polymorphic - a tool call returns either a `SuccessResponse` or an `ErrorResponse`, an input is either `TextInput` or `ImageInput`. Python handles this naturally with `Union[SuccessResponse, ErrorResponse]` and Pydantic's discriminated unions route to the right type based on a field value. Go's type system has no equivalent. You end up with `interface{}` fields, manual type switches, or separate endpoints - none of which produce correct `anyOf`/`oneOf` JSON schemas for the LLM.

There's also nothing in Go for **parsing partial JSON from streaming LLM responses** - a common need when building real-time UIs.

## godantic

[godantic](https://github.com/deepankarm/godantic) fills this gap. One struct definition with `Field{Name}()` methods gives you:

- **Runtime validation** with typed, testable constraints (no struct tags)
- **JSON schema generation** with LLM-specific transforms (`TransformForOpenAI()`, `TransformForGemini()`)
- **Validated marshaling/unmarshaling** in a single call
- **Discriminated unions** for polymorphic LLM responses
- **[Streaming partial JSON parsing](/posts/streaming-partial-json-llm/)** for real-time output
- **Lifecycle hooks** (`BeforeValidate`, `AfterValidate`) for data transformation

This post shows common patterns for validating LLM outputs with godantic.

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

Adding to our `ContactInfo` from earlier, custom validation logic with `godantic.Validate()`:

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

Generate JSON schemas for OpenAI, Gemini, or Anthropic structured outputs using `godantic/schema`:

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

Use the generated schema with OpenAI's structured output API (using [`openai-go`](https://github.com/openai/openai-go)):

```go
// Generate schema
schemaGen := schema.NewGenerator[ProductReview]()
flatSchema, err := schemaGen.GenerateFlattened()

// Call OpenAI with structured output
completion, _ := client.Chat.Completions.New(ctx, openai.ChatCompletionNewParams{
    Messages: []openai.ChatCompletionMessageParamUnion{
        openai.SystemMessage("Extract a structured product review."),
        openai.UserMessage(reviewText),
    },
    Model: openai.ChatModelGPT4o2024_08_06,
    ResponseFormat: openai.ChatCompletionNewParamsResponseFormatUnion{
        OfJSONSchema: &openai.ResponseFormatJSONSchemaParam{
            JSONSchema: openai.ResponseFormatJSONSchemaJSONSchemaParam{
                Name:   "product_review",
                Schema: flatSchema,
                Strict: openai.Bool(true),
            },
        },
    },
})

// Validate the response (even with strict mode, validate anyway)
validator := godantic.NewValidator[ProductReview]()
review, errs := validator.Unmarshal([]byte(completion.Choices[0].Message.Content))
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
| `Union[A, B]` | `godantic.Union[any]("string", A{}, B{})` |
| `Discriminator("type")` | `godantic.DiscriminatedUnion[T]("type", map)` |
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

One struct definition, one source of truth — for what the LLM should produce and what your code will accept.

---
