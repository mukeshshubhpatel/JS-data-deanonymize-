import spacy
from presidio_analyzer import AnalyzerEngine
from presidio_analyzer import PatternRecognizer, RecognizerResult
from presidio_analyzer import PatternRecognizer, Pattern
from presidio_anonymizer import AnonymizerEngine
from presidio_anonymizer.entities import OperatorConfig
import regex as re

# Global variables for reuse
nlp = None
analyzer = None
anonymizer = None
address_recognizer = None

def initialize_nlp_components():
    """Initialize NLP components once instead of on each function call"""
    global nlp, analyzer, anonymizer, address_recognizer
    
    nlp = spacy.load("en_core_web_sm", disable=["ner"]) # Disable NER if not needed for performance
    analyzer = AnalyzerEngine()
    anonymizer = AnonymizerEngine()

    # Register custom recognizers
    # Address recognizer
    address_recognizer = PatternRecognizer(
        supported_entity="ADDRESS",
        patterns=[
            Pattern(
                name="address_pattern",
                regex=r"\b\d{1,5}\s\w+(?:\s\w+)*\s(?:Street|St|Avenue|Ave|Boulevard|Blvd|Road|Rd|Lane|Ln|Drive|Dr|Court|Ct|Way|Square|Sq|Plaza|Plz|Trail|Trl|Terrace|Ter|Place|Pl|Parkway|Pkwy|Loop)\b",
                score=0.85
            ),
            Pattern(
                name="address_with_city",
                regex=r"\b\d{1,5}\s\w+(?:\s\w+)*,\s?\w+(?:\s\w+)*(?:,\s?[A-Za-z]{2}\s?\d{5})?\b",
                score=0.85
            ),
            Pattern(
                name="address_with_zip",
                regex=r"\b\d{1,5}\s[\w\s]+,\s*\w+\s*,\s*[A-Z]{2}\s*\d{5}(?:-\d{4})?\b",
                score=0.9
            ),
            Pattern(
                name="po_box",
                regex=r"\bP\.?O\.?\s*Box\s+\d+\b",
                score=0.85
            ),
        ]
    )
    
    # Date recognizer (needed for proper date detection)
    date_recognizer = PatternRecognizer(
        supported_entity="DATE",
        patterns=[
            Pattern(
                name="date_mmddyyyy",
                regex=r"\b(0?[1-9]|1[0-2])[\/\-](0?[1-9]|[12]\d|3[01])[\/\-](19|20)?\d{2}\b",
                score=0.85
            ),
            Pattern(
                name="date_month_dd_yyyy",
                regex=r"\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+(?:0?[1-9]|[12]\d|3[01])(?:st|nd|rd|th)?,?\s+(?:19|20)?\d{2}\b",
                score=0.85
            ),
            Pattern(
                name="date_dd_month_yyyy",
                regex=r"\b(?:0?[1-9]|[12]\d|3[01])(?:st|nd|rd|th)?\s+(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+(?:19|20)?\d{2}\b",
                score=0.85
            ),
            Pattern(
                name="date_yyyy_mm_dd",
                regex=r"\b(?:19|20)?\d{2}[\/\-](0?[1-9]|1[0-2])[\/\-](0?[1-9]|[12]\d|3[01])\b",
                score=0.85
            ),
        ]
    )

    analyzer.registry.add_recognizer(address_recognizer)
    analyzer.registry.add_recognizer(date_recognizer)

# Cache for medical entities to avoid repeat processing
medical_entities_cache = {}

def extract_drugs_and_medical_terms(raw_data):
    # Check cache first
    if raw_data in medical_entities_cache:
        return medical_entities_cache[raw_data]
    
    global nlp
    if nlp is None:
        initialize_nlp_components()
        
    doc = nlp(raw_data)
    recognized_entities = []
    for ent in doc.ents:
        if ent.label_ in ["DISEASE", "DRUG", "MEDICAL_TERM"]:
            recognized_entities.append(ent.text)
    
    result = set(recognized_entities)
    # Store in cache
    medical_entities_cache[raw_data] = result
    return result

# Original function (kept for backward compatibility)
def anonymize_with_presidio_selective(raw_data, names_list, options):
    global analyzer, anonymizer
    if analyzer is None or anonymizer is None:
        initialize_nlp_components()
        
    medical_entities = extract_drugs_and_medical_terms(raw_data)
    
    # Define entities to analyze based on options
    entities = []
    if options['date']:
        entities.append("DATE")
    if options['name']:
        entities.append("PERSON")
    if options['email']:
        entities.append("EMAIL_ADDRESS")
    if options['phone']:
        entities.append("PHONE_NUMBER")
    if options['id']:
        entities.append("ID")
    if options['address']:
        entities.append("ADDRESS")

    # Analyze text using Presidio with selected entities
    analysis_results = analyzer.analyze(
        text=raw_data,
        language="en",
        entities=entities
    )

    # Configure anonymization operators based on options
    anonymization_config = {}
    
    if options['date']:
        anonymization_config["DATE"] = OperatorConfig("replace", {"new_value": "[Date_Anonymized]"})
    if options['name']:
        anonymization_config["PERSON"] = OperatorConfig("replace", {"new_value": "[Name_Anonymized]"})
    if options['email']:
        anonymization_config["EMAIL_ADDRESS"] = OperatorConfig("replace", {"new_value": "[Email_Anonymized]"})
    if options['phone']:
        anonymization_config["PHONE_NUMBER"] = OperatorConfig("replace", {"new_value": "[Phone_Anonymized]"})
    if options['id']:
        anonymization_config["ID"] = OperatorConfig("replace", {"new_value": "[ID_Anonymized]"})
    if options['address']:
        anonymization_config["ADDRESS"] = OperatorConfig("replace", {"new_value": "[Address_Anonymized]"})

    # Anonymize the text
    # Check if we have any results to process
    if analysis_results:
        anonymized_result = anonymizer.anonymize(
            text=raw_data,
            analyzer_results=analysis_results,
            operators=anonymization_config
        )
        final_text = anonymized_result.text
    else:
        # If no analysis results, just use the raw data
        final_text = raw_data

    # Ensure drugs and medical terms are not anonymized
    for entity in medical_entities:
        anonymized_result.text = re.sub(
            rf'\b{re.escape(entity)}\b',  # Escape special characters in entity
            entity,
            anonymized_result.text,
            flags=re.IGNORECASE
        )

    # Anonymize names from the provided list if name option is selected
    if options['name'] and names_list:
        # Compile one big regex for all names (more efficient)
        names_pattern = '|'.join(re.escape(name) for name in names_list if name not in medical_entities)
        if names_pattern:
            anonymized_result.text = re.sub(
                rf'\b({names_pattern})\b',
                '[Name_Anonymized]',
                anonymized_result.text,
                flags=re.IGNORECASE
            )

    return anonymized_result.text

# New batch processing function that processes the entire text at once 
def anonymize_with_presidio_selective_batch(raw_data, names_list, options):
    """Process the entire text at once instead of line by line"""
    global analyzer, anonymizer
    if analyzer is None or anonymizer is None:
        initialize_nlp_components()
    
    # Initialize final_text with the raw data as default
    final_text = raw_data
        
    medical_entities = extract_drugs_and_medical_terms(raw_data)
    
    # Define entities to analyze based on options
    entities = []
    if options['date']:
        entities.append("DATE")
    if options['name']:
        entities.append("PERSON")
    if options['email']:
        entities.append("EMAIL_ADDRESS")
    if options['phone']:
        entities.append("PHONE_NUMBER")
    if options['id']:
        entities.append("US_DRIVER_LICENSE")  # Using built-in license detector
        entities.append("US_PASSPORT")        # Using built-in passport detector
    if options['address']:
        entities.append("ADDRESS")

    # If no entities are selected, return raw data
    if not entities:
        return raw_data
        
    # Skip processing if we're just processing emails in the Streamlit app
    # This is a workaround for the email/name conflict
    if len(entities) == 1 and entities[0] == "EMAIL_ADDRESS":
        # Just replace all detected emails
        email_pattern = re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b')
        return email_pattern.sub("[Email_Anonymized]", raw_data)

    # Configure anonymization operators based on options
    anonymization_config = {}
    
    if options['date']:
        anonymization_config["DATE"] = OperatorConfig("replace", {"new_value": "[Date_Anonymized]"})
    if options['name']:
        anonymization_config["PERSON"] = OperatorConfig("replace", {"new_value": "[Name_Anonymized]"})
    if options['email']:
        anonymization_config["EMAIL_ADDRESS"] = OperatorConfig("replace", {"new_value": "[Email_Anonymized]"})
    if options['phone']:
        anonymization_config["PHONE_NUMBER"] = OperatorConfig("replace", {"new_value": "[Phone_Anonymized]"})
    if options['id']:
        anonymization_config["US_DRIVER_LICENSE"] = OperatorConfig("replace", {"new_value": "[ID_Anonymized]"})
        anonymization_config["US_PASSPORT"] = OperatorConfig("replace", {"new_value": "[ID_Anonymized]"})
    if options['address']:
        anonymization_config["ADDRESS"] = OperatorConfig("replace", {"new_value": "[Address_Anonymized]"})

    # Analyze text using Presidio with selected entities
    # Use try-except to handle the case where no recognizers are found
    try:
        analysis_results = analyzer.analyze(
            text=raw_data,
            language="en",
            entities=entities,
            ad_hoc_recognizers=[]  # No custom recognizers for speed
        )
    except ValueError as e:
        # If no recognizers found, return the raw data
        if "No matching recognizers were found" in str(e):
            print(f"Warning: {e}")
            return raw_data
        else:
            # Re-raise if it's a different error
            raise

    # Anonymize the text
    # Check if we have any results to process
    if analysis_results:
        try:
            anonymized_result = anonymizer.anonymize(
                text=raw_data,
                analyzer_results=analysis_results,
                operators=anonymization_config
            )
            final_text = anonymized_result.text
        except Exception as e:
            print(f"Error in anonymization: {e}")
            return raw_data

    # Configure anonymization operators based on options
    anonymization_config = {}
    
    if options['date']:
        anonymization_config["DATE"] = OperatorConfig("replace", {"new_value": "[Date_Anonymized]"})
    if options['name']:
        anonymization_config["PERSON"] = OperatorConfig("replace", {"new_value": "[Name_Anonymized]"})
    if options['email']:
        anonymization_config["EMAIL_ADDRESS"] = OperatorConfig("replace", {"new_value": "[Email_Anonymized]"})
    if options['phone']:
        anonymization_config["PHONE_NUMBER"] = OperatorConfig("replace", {"new_value": "[Phone_Anonymized]"})
    if options['id']:
        anonymization_config["ID"] = OperatorConfig("replace", {"new_value": "[ID_Anonymized]"})
    if options['address']:
        anonymization_config["ADDRESS"] = OperatorConfig("replace", {"new_value": "[Address_Anonymized]"})

    # Anonymize the text
    anonymized_result = anonymizer.anonymize(
        text=raw_data,
        analyzer_results=analysis_results,
        operators=anonymization_config
    )

    # Ensure drugs and medical terms are not anonymized (process once)
    if medical_entities:
        medical_pattern = '|'.join(re.escape(entity) for entity in medical_entities)
        # Function to replace with the original entity
        def replace_with_original(match):
            return match.group(0)
            
        final_text = re.sub(
            rf'\b({medical_pattern})\b',
            replace_with_original,
            final_text,
            flags=re.IGNORECASE
        )

    # Anonymize names from the provided list if name option is selected (process once)
    if options['name'] and names_list:
        # Filter names against medical entities and ensure all are strings
        filtered_names = []
        for name in names_list:
            if name not in medical_entities:
                # Convert to string if it's not already a string
                if not isinstance(name, str):
                    name = str(name)
                # Only add non-empty strings
                if name.strip():
                    filtered_names.append(name)
        
        if filtered_names:
            # Create chunks of names to avoid regex overflow
            chunk_size = 500  # Adjust based on system capability
            for i in range(0, len(filtered_names), chunk_size):
                chunk = filtered_names[i:i+chunk_size]
                try:
                    names_pattern = '|'.join(re.escape(str(name)) for name in chunk)
                    
                    final_text = re.sub(
                        rf'\b({names_pattern})\b',
                        '[Name_Anonymized]',
                        final_text,
                        flags=re.IGNORECASE
                    )
                except Exception as e:
                    print(f"Error processing names chunk: {e}")

    return final_text