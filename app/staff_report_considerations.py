"""Optional titled considerations for the Online module verification sections."""
import json


def sections(record):
    if record.format != 'Online':
        return ()
    modules = {module.lower() for module in record.modules_list()}
    return tuple(key for key, module in [('reading_writing', 'reading and writing'), ('listening', 'listening and speaking')]
                 if module in modules)


def validate(record, form):
    values = {}
    for section in sections(record):
        try:
            entries = json.loads(form.get('important_considerations_' + section, '[]'))
        except (ValueError, TypeError):
            raise ValueError('Enter valid important considerations.')
        if not isinstance(entries, list) or len(entries) > 500:
            raise ValueError('Enter a list of important considerations (maximum 500 per section).')
        clean = []
        for entry in entries:
            if not isinstance(entry, dict):
                raise ValueError('Complete Title and Text for every important consideration.')
            title, text = entry.get('title'), entry.get('text')
            if not isinstance(title, str) or not isinstance(text, str) or not title.strip() or not text.strip():
                raise ValueError('Complete Title and Text for every important consideration.')
            if len(title.strip()) > 200 or len(text.strip()) > 10000:
                raise ValueError('Important consideration Title must not exceed 200 characters and Text must not exceed 10,000 characters.')
            clean.append(dict(title=title.strip(), text=text.strip()))
        values[section] = clean
    return values
