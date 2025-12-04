"""
Structured intake question management.
Loads questions from Salesforce intake_with_sections.json and manages flow.
"""

import json
import os
from typing import Dict, List, Optional, Any
from dataclasses import dataclass

@dataclass
class IntakeQuestion:
    """Represents a single intake question."""
    api_name: str
    label: str
    field_type: str
    section: str
    required: bool
    help_text: str
    picklist_values: Optional[List[Dict[str, Any]]] = None
    depends_on: Optional[str] = None  # Field this question depends on
    depends_on_value: Optional[str] = None  # Value that triggers this question
    confirmation_type: Optional[str] = None  # "spelling", "digits", "none"


class IntakeQuestionManager:
    """Manages the structured intake question flow."""
    
    # Ordered sections as specified by user
    SECTION_ORDER = [
        "Client Contact Information",
        "Emergency Contact",
        "Defendant Information",
        "Employment Timeline",
        "Employment Information",
        "New Employment Since Termination",
        "Work Schedule",
        "Workplace Discipline",
        "Wage And Hour Claims",
        "Regular Time Pay",
        "Overtime Pay",
        "Rest Breaks",
        "Meal Periods",
        "Personal Property",
        "Protected Activities",
        "FEHA",
        "Sexual Harassment",
        "Sick Leave",
        "Medical/Family Leave",
        "Miscellaneous Complaints",
        "Witnesses"
    ]
    
    # Fields that need spelling confirmation
    SPELLING_CONFIRMATION_FIELDS = [
        "Client_Name__c",
        "Client_Email__c",
        "Emergency_Contact_Name__c"
    ]
    
    # Fields that need digit readback
    DIGIT_CONFIRMATION_FIELDS = [
        "Client_Phone_Number__c",
        "Emergency_Contact_Phone__c"
    ]
    
    # Conditional logic rules
    CONDITIONAL_RULES = {
        # Personal Property questions depend on answering "Yes" to this:
        "Required_to_Use_Personal_Property__c": {
            "triggers_when": "Yes",
            "dependent_fields": [
                "Personal_Property_Cell_Phone__c",
                "Personal_Property_Vehicle__c",
                "Personal_Property_Computer__c",
                "Personal_Property_Home__c",
                "Personal_Property_Other__c",
                "Personal_Property_Details__c",
                "Personal_Property_Reimbursed__c",
                # Add all 22 personal property fields here
            ]
        },
        # More conditional rules can be added here
    }
    
    def __init__(self, json_path: str = None):
        """Initialize with Salesforce intake fields."""
        if json_path is None:
            # Default to intake_with_sections.json in AI_Voice directory
            json_path = os.path.join(
                os.path.dirname(os.path.dirname(__file__)),
                "intake_with_sections.json"
            )
        
        self.json_path = json_path
        self.questions: List[IntakeQuestion] = []
        self.questions_by_section: Dict[str, List[IntakeQuestion]] = {}
        self.questions_by_api_name: Dict[str, IntakeQuestion] = {}
        
        self._load_questions()
    
    def _load_questions(self):
        """Load questions from Salesforce JSON file."""
        with open(self.json_path, 'r') as f:
            data = json.load(f)
        
        fields = data.get('fields', [])
        
        # Map section names (handle variations)
        section_mapping = {
            "Client Contact Information": "Client Contact Information",
            "Emergency Contact": "Emergency Contact",
            "Defendant Information": "Defendant Information",
            "Employment Timeline": "Employment Timeline",
            "Employment Information": "Employment Information",
            "New Employment Since Termination": "New Employment Since Termination",
            "Work Schedule": "Work Schedule",
            "Workplace Discipline": "Workplace Discipline",
            "Wage And Hour Claims": "Wage And Hour Claims",
            "Regular Time Pay": "Regular Time Pay",
            "Overtime Pay": "Overtime Pay",
            "Rest Breaks": "Rest Breaks",
            "Meal Periods": "Meal Periods",  # Note: might be "Meal Period" in SF
            "Personal Property": "Personal Property",
            "Protected Activities": "Protected Activities",
            "FEHA": "FEHA",
            "Sexual Harassment": "Sexual Harassment",
            "Sick Leave": "Sick Leave",
            "Medical/Family Leave": "Medical/Family Leave",
            "Miscellaneous Complaints": "Miscellaneous Complaints",
            "Witnesses": "Witnesses"
        }
        
        # Create questions for each field
        for field in fields:
            section = field.get('section')
            if not section:
                continue
            
            # Map to standardized section name
            standardized_section = None
            for std_name, sf_name in section_mapping.items():
                if section.lower() == sf_name.lower():
                    standardized_section = std_name
                    break
            
            if not standardized_section:
                # Skip sections not in our list
                continue
            
            # Determine confirmation type
            confirmation_type = None
            api_name = field['api_name']
            if api_name in self.SPELLING_CONFIRMATION_FIELDS:
                confirmation_type = "spelling"
            elif api_name in self.DIGIT_CONFIRMATION_FIELDS:
                confirmation_type = "digits"
            
            # Check if this field has conditional dependencies
            depends_on = None
            depends_on_value = None
            for trigger_field, rule in self.CONDITIONAL_RULES.items():
                if api_name in rule.get('dependent_fields', []):
                    depends_on = trigger_field
                    depends_on_value = rule['triggers_when']
                    break
            
            question = IntakeQuestion(
                api_name=api_name,
                label=field['label'],
                field_type=field['type'],
                section=standardized_section,
                required=field.get('required', False),
                help_text=field.get('help_text', ''),
                picklist_values=field.get('picklist_values'),
                depends_on=depends_on,
                depends_on_value=depends_on_value,
                confirmation_type=confirmation_type
            )
            
            self.questions.append(question)
            self.questions_by_api_name[api_name] = question
            
            # Add to section mapping
            if standardized_section not in self.questions_by_section:
                self.questions_by_section[standardized_section] = []
            self.questions_by_section[standardized_section].append(question)
        
        print(f"Loaded {len(self.questions)} questions across {len(self.questions_by_section)} sections")
    
    def get_sections(self) -> List[str]:
        """Get ordered list of sections."""
        return [s for s in self.SECTION_ORDER if s in self.questions_by_section]
    
    def get_questions_for_section(
        self, 
        section: str,
        collected_fields: Dict[str, Any] = None
    ) -> List[IntakeQuestion]:
        """
        Get questions for a section, filtering by conditional logic.
        
        Args:
            section: Section name
            collected_fields: Already collected field values (for conditionals)
        
        Returns:
            List of questions to ask in this section
        """
        if collected_fields is None:
            collected_fields = {}
        
        all_questions = self.questions_by_section.get(section, [])
        
        # Filter based on conditional logic
        questions_to_ask = []
        for question in all_questions:
            # Check if question has a dependency
            if question.depends_on:
                trigger_value = collected_fields.get(question.depends_on)
                if trigger_value != question.depends_on_value:
                    # Dependency not met, skip this question
                    continue
            
            questions_to_ask.append(question)
        
        return questions_to_ask
    
    def get_next_question(
        self,
        current_section: str,
        collected_fields: Dict[str, Any]
    ) -> Optional[IntakeQuestion]:
        """
        Get the next unanswered question in the current section.
        
        Args:
            current_section: Current section name
            collected_fields: Already collected field values
        
        Returns:
            Next question to ask, or None if section is complete
        """
        questions = self.get_questions_for_section(current_section, collected_fields)
        
        for question in questions:
            if question.api_name not in collected_fields:
                return question
        
        return None
    
    def is_section_complete(
        self,
        section: str,
        collected_fields: Dict[str, Any]
    ) -> bool:
        """Check if all required questions in a section are answered."""
        questions = self.get_questions_for_section(section, collected_fields)
        
        for question in questions:
            # Skip non-required questions
            if not question.required:
                continue
            
            if question.api_name not in collected_fields:
                return False
        
        return True
    
    def validate_answer(
        self,
        question: IntakeQuestion,
        answer: str
    ) -> tuple[bool, Optional[str]]:
        """
        Validate an answer against the question's constraints.
        
        Returns:
            (is_valid, error_message)
        """
        # Picklist validation
        if question.picklist_values:
            valid_values = [pv['value'] for pv in question.picklist_values]
            if answer not in valid_values:
                # Try case-insensitive match
                answer_lower = answer.lower()
                for valid_value in valid_values:
                    if valid_value.lower() == answer_lower:
                        return True, None
                
                return False, f"Please choose from: {', '.join(valid_values)}"
        
        # Type validation
        if question.field_type == 'email':
            if '@' not in answer:
                return False, "Please provide a valid email address"
        
        if question.field_type == 'phone':
            # Basic phone validation
            digits = ''.join(c for c in answer if c.isdigit())
            if len(digits) < 10:
                return False, "Please provide a valid phone number"
        
        if question.field_type == 'date':
            # Could add date parsing validation here
            pass
        
        return True, None
    
    def should_confirm_value(
        self,
        question: IntakeQuestion,
        prefilled_value: Any
    ) -> bool:
        """Check if a pre-filled value should be confirmed vs re-asked."""
        return prefilled_value is not None and prefilled_value != ""
    
    def format_question_prompt(
        self,
        question: IntakeQuestion,
        prefilled_value: Any = None
    ) -> str:
        """
        Format the question prompt for the LLM.
        
        Args:
            question: The question to ask
            prefilled_value: Pre-filled value if exists
        
        Returns:
            Formatted prompt string
        """
        if prefilled_value:
            # Confirm pre-filled value
            prompt = f"I have your {question.label.lower()} as: {prefilled_value}. Is that correct?"
        else:
            # Check if help_text is conversational (not UI instructions)
            has_good_help_text = False
            if question.help_text:
                help_lower = question.help_text.lower()
                # Skip help_text that has UI-specific instructions
                if not any(word in help_lower for word in ['select', 'choose', 'click', 'check', 'enter']):
                    has_good_help_text = True
                    prompt = question.help_text
            
            if not has_good_help_text:
                # Use label or create conversational question
                if question.label.startswith("What") or "?" in question.label:
                    # Already a question
                    prompt = question.label
                else:
                    # Convert label to conversational question with variety
                    label_lower = question.label.lower()
                    
                    # More natural phrasing based on field type
                    if question.field_type == "date":
                        if "birth" in label_lower:
                            prompt = f"What's your date of birth?"
                        else:
                            prompt = f"Can you tell me the {label_lower}?"
                    elif question.field_type == "phone":
                        if "emergency" in label_lower:
                            prompt = f"What's the {label_lower}?"
                        else:
                            prompt = f"What phone number can I reach you at?"
                    elif question.field_type == "email":
                        if "emergency" in label_lower or "contact" in label_lower:
                            prompt = f"And what's the {label_lower}?"
                        else:
                            prompt = f"What email address should we use?"
                    elif question.field_type == "picklist":
                        # Make it more conversational
                        prompt = question.label if "?" in question.label else f"Can you tell me about your {label_lower}?"
                    elif question.field_type == "textarea" or question.field_type == "string":
                        # Name fields, addresses, etc.
                        if "name" in label_lower:
                            prompt = f"What is the {label_lower}?"
                        elif "address" in label_lower:
                            prompt = f"What's the {label_lower}?"
                        else:
                            prompt = f"Can you tell me the {label_lower}?"
                    else:
                        prompt = f"Can you tell me your {label_lower}?"
        
        return prompt
    
    def get_confirmation_instructions(self, question: IntakeQuestion) -> Optional[str]:
        """Get specific confirmation instructions for a field."""
        if question.confirmation_type == "spelling":
            return (
                "After they answer, confirm the spelling using phonetic alphabet. "
                "Example: 'That's J as in juliet, O as in oscar, H as in hotel, N as in november?'"
            )
        elif question.confirmation_type == "digits":
            return (
                "After they answer, read back the digits with pauses. "
                "Example: '5, 5, 5. 1, 2, 3. 4, 5, 6, 7. Is that correct?'"
            )
        return None
