import re

# Necessary for look-alike alphanumeric characters according to the Nigerian license pate detection
dict_char_to_int = {'O': '0',
                    'I': '1',
                    'J': '3',
                    'A': '4',
                    'G': '6',
                    'S': '5'}

dict_int_to_char = {'0': 'O',
                    '1': 'I',
                    '3': 'J',
                    '4': 'A',
                    '6': 'G',
                    '5': 'S'}

              

def character_replacement(text):
     """
      Ensures that the characters in the text align with the Nigerian plate format
      Prevents the mistakes of numbers and letters
      
      Args:
        text: a string of characters to be checked and replaced if necessary
      
      Returns:
        str: the text with the characters replaced if necessary
     
     """
     if len(text) != 8:
          return None
     text = text.upper()
     license_plate = ''
     mapping = {0: dict_int_to_char, 1: dict_int_to_char, 
                2: dict_int_to_char, 3: dict_char_to_int,
                4: dict_char_to_int, 5: dict_char_to_int,
                6: dict_int_to_char, 7: dict_int_to_char}
     
     for j in [0, 1, 2, 3, 4, 5, 6, 7]:
         if text[j] in mapping[j].keys():
             license_plate += mapping[j][text[j]]
         else:
             license_plate += text[j]

     return license_plate

    

def check_ocr_output(list):
      """      
      Checks the output list of strings from OCR and returns the first string that matches the pattern

      Args:
        list: list of strings from the output of the OCR

      Returns:
        str: the first string that matches the pattern of Nigerian plates, 
        None: if no match is found
                  
      """
      
      unwanted_characters = '!"#$%&\'()*+,-./:;<=>?@[\\]^_`{|}~ '
      pattern = re.compile(r'[a-zA-Z]\d')
      for scan in list:
          # if len(scan) <  
          for character in unwanted_characters:
               scan = scan.replace(character, '')
          if pattern.search(scan):
                return character_replacement(scan)  #To ensure it aligns with the Nigerian plate format
                
      return None

