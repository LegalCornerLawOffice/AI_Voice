# Structured Intake System

## Overview

This system replaces the freeform conversation flow with a **structured question-by-question** intake process that:

✅ Follows exact section order from Salesforce
✅ Handles conditional logic (e.g., Personal Property questions)
✅ Confirms pre-filled values instead of re-asking
✅ Validates answers against picklist options
✅ Tracks individual field completion in Redis
✅ Supports spelling/digit confirmations

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    STRUCTURED INTAKE FLOW                        │
└─────────────────────────────────────────────────────────────────┘

1. Load Questions from Salesforce
   ↓
   IntakeQuestionManager
   - Reads intake_with_sections.json
   - Builds question objects with metadata
   - Maps conditional dependencies

2. Initialize Session with Pre-filled Data
   ↓
   StructuredIntakeState (Redis)
   {
     "fields": {"Client_Name__c": "John Doe"},  // Pre-filled
     "current_section": "Client Contact Information",
     "current_question_index": 0
   }

3. Get Next Question
   ↓
   question_manager.get_next_question(section, collected_fields)
   - Filters by conditional logic
   - Skips already-answered fields
   - Returns next IntakeQuestion

4. Format Question
   ↓
   IF field has pre-filled value:
     → "I have your name as John Doe. Is that correct?"
   ELSE:
     → "What is your full name?"

5. User Answers
   ↓
   - Validate against picklist
   - Store in Redis
   - Confirm if needed (spelling/digits)

6. Move to Next Question
   ↓
   Repeat steps 3-5 until section complete

7. Advance to Next Section
   ↓
   state.advance_section("Emergency Contact")
```

---

## Key Components

### 1. IntakeQuestionManager (`conversation/intake_questions.py`)

**Purpose:** Loads and manages Salesforce intake questions

**Key Methods:**
- `get_sections()` → Returns ordered list of sections
- `get_questions_for_section(section, collected_fields)` → Returns questions to ask (filtered by conditionals)
- `get_next_question(section, collected_fields)` → Returns next unanswered question
- `validate_answer(question, answer)` → Validates against picklist/type
- `format_question_prompt(question, prefilled_value)` → Generates prompt for LLM

**Conditional Logic:**
```python
CONDITIONAL_RULES = {
    "Required_to_Use_Personal_Property__c": {
        "triggers_when": "Yes",
        "dependent_fields": [
            "Personal_Property_Cell_Phone__c",
            "Personal_Property_Vehicle__c",
            # ... 20 more fields
        ]
    }
}
```

### 2. StructuredIntakeState (`services/structured_intake_state.py`)

**Purpose:** Tracks intake progress in Redis

**Redis Structure:**
```json
{
  "session_id": "abc-123",
  "current_section": "Client Contact Information",
  "current_question_index": 2,
  "fields": {
    "Client_Name__c": "John Doe",
    "Client_Phone_Number__c": "555-1234"
  },
  "confirmed_fields": ["Client_Name__c"],
  "pending_confirmation": {
    "field": "Client_Phone_Number__c",
    "value": "555-1234",
    "asked_at": "2025-12-04T12:00:00"
  },
  "conditional_flags": {
    "has_personal_property": true
  },
  "section_progress": {
    "Client Contact Information": "in_progress",
    "Emergency Contact": "not_started"
  }
}
```

**Key Methods:**
- `set_field_value(session_id, api_name, value, confirmed)` → Store answer
- `get_prefilled_value(session_id, api_name)` → Check if pre-filled
- `set_pending_confirmation(session_id, api_name, value)` → Mark for confirmation
- `set_conditional_flag(session_id, flag, value)` → Track conditional triggers
- `advance_section(session_id, new_section)` → Move to next section

---

## Section Order

```python
SECTION_ORDER = [
    1.  "Client Contact Information",
    2.  "Emergency Contact",
    3.  "Defendant Information",
    4.  "Employment Timeline",
    5.  "Employment Information",
    6.  "New Employment Since Termination",
    7.  "Work Schedule",
    8.  "Workplace Discipline",
    9.  "Wage And Hour Claims",
    10. "Regular Time Pay",
    11. "Overtime Pay",
    12. "Rest Breaks",
    13. "Meal Periods",
    14. "Personal Property",
    15. "Protected Activities",
    16. "FEHA",
    17. "Sexual Harassment",
    18. "Sick Leave",
    19. "Medical/Family Leave",
    20. "Miscellaneous Complaints",
    21. "Witnesses"
]
```

---

## Conditional Logic Examples

### Personal Property (22 dependent questions)

```
Question: "Were you required to use personal property for work?"
Answer: "Yes"
   ↓
Triggers 22 follow-up questions:
  - Personal Property: Cell Phone?
  - Personal Property: Vehicle?
  - Personal Property: Computer?
  - ...
  - Were you reimbursed?
  - Details of usage?

Answer: "No"
   ↓
Skip all 22 follow-up questions, move to next section
```

### Implementation:
```python
# When user answers "Yes" to Required_to_Use_Personal_Property__c:
await state.set_conditional_flag(session_id, "has_personal_property", True)
await state.set_field_value(session_id, "Required_to_Use_Personal_Property__c", "Yes")

# Later, when getting questions for Personal Property section:
questions = question_manager.get_questions_for_section(
    "Personal Property",
    collected_fields=await state.get_collected_fields(session_id)
)
# Returns all 24 questions because dependency was met
```

---

## Pre-filled Value Confirmation

### Without Pre-fill:
```
AI: "What is your full name?"
User: "John Doe"
AI: "Let me confirm: J as in juliet, O as in oscar, H as in hotel, N as in november, then D as in delta, O as in oscar, E as in echo?"
User: "Correct"
```

### With Pre-fill (from case evaluation):
```
AI: "I have your name as John Doe. Is that correct?"
User: "Yes"
AI: [Moves to next question - no spelling confirmation needed]
```

### Implementation:
```python
prefilled_value = await state.get_prefilled_value(session_id, "Client_Name__c")

if prefilled_value:
    prompt = f"I have your {question.label.lower()} as: {prefilled_value}. Is that correct?"
else:
    prompt = question.label
```

---

## Validation

### Picklist Fields:
```python
question = IntakeQuestion(
    api_name="Were_you_fired_or_did_you_resign__c",
    picklist_values=[
        {"value": "Fired", "label": "Fired"},
        {"value": "Resigned", "label": "Resigned"},
        {"value": "Laid Off", "label": "Laid Off"}
    ]
)

# User says: "I was terminated"
is_valid, error = question_manager.validate_answer(question, "I was terminated")
# Returns: (False, "Please choose from: Fired, Resigned, Laid Off")

# LLM can then re-ask with options
```

---

## Next Steps to Integrate

1. **Update audio_pipeline.py:**
   - Replace freeform LLM with structured question flow
   - Use `IntakeQuestionManager` to get next question
   - Use `StructuredIntakeState` instead of basic state manager

2. **Update prompts.py:**
   - Simplify to just "Ask this question" + confirmation instructions
   - Remove section-based freeform prompts

3. **Handle confirmations:**
   - Spelling confirmations for names/emails
   - Digit readback for phone numbers
   - Yes/no confirmations for pre-filled values

4. **Conditional logic:**
   - Check trigger fields before showing dependent questions
   - Update conditional flags in Redis

Would you like me to integrate this into the audio_pipeline now?
