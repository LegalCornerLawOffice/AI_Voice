"""
Conversation flow logic and state machine.
"""

import logging
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)


class ConversationFlow:
    """
    Manages conversation flow through intake sections.
    
    Sections:
    1. GREETING - Welcome and explain process
    2. BASIC_INFO - Name, contact info, demographics
    3. EMPLOYMENT_BASICS - Employer, position, dates
    4. WORK_DETAILS - Job duties, schedule
    5. PAY_ISSUES - Wage/hour violations
    6. DISCRIMINATION - FEHA protected classes
    7. HARASSMENT - Sexual or other harassment
    8. TERMINATION - How/why employment ended
    9. CLOSING - Wrap up and next steps
    """
    
    SECTIONS = [
        "GREETING",
        "BASIC_INFO",
        "EMPLOYMENT_BASICS",
        "WORK_DETAILS",
        "PAY_ISSUES",
        "DISCRIMINATION",
        "HARASSMENT",
        "TERMINATION",
        "CLOSING"
    ]
    
    # Fields required for each section (simplified for MVP)
    SECTION_FIELDS = {
        "GREETING": [],
        "BASIC_INFO": [
            "Client_Name__c",
            "Date_Of_Birth__c",
            "Client_Address__c",
            "Client_Phone_Number__c",
            "Client_Email__c"
        ],
        "EMPLOYMENT_BASICS": [
            "Name_Of_Employer__c",
            "Position_Title__c",
            "Start_Date_of_Employment__c",
            "Are_you_still_working_for_this_employer__c",
            "Hourly_Or_Salary__c"
        ],
        "WORK_DETAILS": [
            "Describe_all_of_your_job_duties__c",
            "What_is_your_work_schedule__c",
            "Hours_Worked_per_Week__c"
        ],
        "PAY_ISSUES": [
            "Unpaid_Regular_Hours__c",
            "Unpaid_Overtime__c",
            "Work_Off_The_Clock__c"
        ],
        "DISCRIMINATION": [
            "FEHA__c",
            "Race_Color__c",
            "Age_40_or_over__c",
            "Sex_or_Gender__c"
        ],
        "HARASSMENT": [
            "Sexual_Harassment_Assault__c",
            "Incident_Type__c"
        ],
        "TERMINATION": [
            "Were_you_fired_or_did_you_resign__c",
            "Termination_Date__c",
            "Why_do_YOU_believe_you_were_terminated__c"
        ],
        "CLOSING": []
    }
    
    def __init__(self):
        self.current_section_index = 0
    
    def get_current_section(self) -> str:
        """Get current section name."""
        if self.current_section_index < len(self.SECTIONS):
            return self.SECTIONS[self.current_section_index]
        return "CLOSING"
    
    def advance_section(self) -> str:
        """Move to next section."""
        self.current_section_index += 1
        section = self.get_current_section()
        logger.info(f"Advanced to section: {section}")
        return section
    
    def is_section_complete(
        self,
        section: str,
        collected_fields: Dict[str, Any]
    ) -> bool:
        """
        Check if section has enough information to continue.
        
        Args:
            section: Section name
            collected_fields: Fields collected so far
        
        Returns:
            bool: True if section is complete enough
        """
        required_fields = self.SECTION_FIELDS.get(section, [])
        
        if not required_fields:
            # Sections without required fields (greeting, closing)
            return True
        
        # Check if at least 60% of fields are collected
        collected_count = sum(
            1 for field in required_fields
            if field in collected_fields
        )
        
        completion_rate = collected_count / len(required_fields)
        
        logger.debug(f"Section {section} completion: {completion_rate:.0%}")
        
        return completion_rate >= 0.6
    
    def should_ask_about_discrimination(
        self,
        collected_fields: Dict[str, Any]
    ) -> bool:
        """Check if we should ask discrimination questions."""
        # Ask if they mentioned anything related to discrimination
        termination_reason = collected_fields.get(
            "Why_do_YOU_believe_you_were_terminated__c", {}
        ).get("value", "")
        
        keywords = [
            "discrimin", "unfair", "treat", "age", "race",
            "gender", "sex", "disability", "religion"
        ]
        
        return any(kw in termination_reason.lower() for kw in keywords)
    
    def should_ask_about_harassment(
        self,
        collected_fields: Dict[str, Any]
    ) -> bool:
        """Check if we should ask harassment questions."""
        # Ask if they mentioned harassment
        job_duties = collected_fields.get(
            "Describe_all_of_your_job_duties__c", {}
        ).get("value", "")
        
        termination_reason = collected_fields.get(
            "Why_do_YOU_believe_you_were_terminated__c", {}
        ).get("value", "")
        
        combined = (job_duties + " " + termination_reason).lower()
        
        keywords = [
            "harass", "inappropriate", "sexual", "hostile",
            "uncomfortable", "assault"
        ]
        
        return any(kw in combined for kw in keywords)
    
    def get_next_section(
        self,
        current_section: str,
        collected_fields: Dict[str, Any]
    ) -> Optional[str]:
        """
        Determine next section based on conversation flow.
        
        Implements branching logic:
        - Skip discrimination if not relevant
        - Skip harassment if not mentioned
        
        Args:
            current_section: Current section name
            collected_fields: Fields collected so far
        
        Returns:
            Next section name or None if done
        """
        try:
            current_index = self.SECTIONS.index(current_section)
        except ValueError:
            current_index = 0
        
        next_index = current_index + 1
        
        # Check if we're at the end
        if next_index >= len(self.SECTIONS):
            return None
        
        next_section = self.SECTIONS[next_index]
        
        # Branching logic
        if next_section == "DISCRIMINATION":
            if not self.should_ask_about_discrimination(collected_fields):
                logger.info("Skipping DISCRIMINATION section")
                next_index += 1
                if next_index >= len(self.SECTIONS):
                    return None
                next_section = self.SECTIONS[next_index]
        
        if next_section == "HARASSMENT":
            if not self.should_ask_about_harassment(collected_fields):
                logger.info("Skipping HARASSMENT section")
                next_index += 1
                if next_index >= len(self.SECTIONS):
                    return None
                next_section = self.SECTIONS[next_index]
        
        logger.info(f"Next section: {next_section}")
        return next_section
