"""English and Spanish copy for the same exam-centre feedback questions."""
QUESTIONS = [
    ('organisation', 'Exam session organisation', 'Organización de la sesión de examen',
     'How would you rate the overall organisation, punctuality and coordination of the exam session?',
     '¿Cómo calificaría la organización general, la puntualidad y la coordinación de la sesión de examen?'),
    ('candidate_experience', 'Candidate experience', 'Experiencia de los candidatos',
     'How would you rate the examination environment, candidate support and overall experience?',
     '¿Cómo calificaría el ambiente del examen, el acompañamiento a los candidatos y su experiencia general?'),
    ('communication', 'Communication and support', 'Comunicación y acompañamiento',
     "How would you rate Path's communication and support before and during the exam session?",
     '¿Cómo calificaría la comunicación y el acompañamiento de Path antes y durante la sesión de examen?'),
    ('overall', 'Overall experience with Path', 'Experiencia general con Path',
     "How would you rate your institution's overall experience working with Path Examinations?",
     '¿Cómo calificaría la experiencia general de su institución al trabajar con Path Examinations?'),
]
OPEN_QUESTIONS = [
    ('worked_well', 'What worked particularly well?', '¿Qué funcionó especialmente bien?', '', '',
     'Share what you valued most...', 'Comparta lo que más valoró...'),
    ('improvements_noticed', 'What improvements have you noticed?', '¿Qué mejoras ha notado?',
     'Compared with previous exam sessions, if applicable.', 'En comparación con sesiones de examen anteriores, si corresponde.',
     'What has changed for the better?', '¿Qué ha cambiado para mejor?'),
    ('improvements_needed', 'What should we improve?', '¿Qué deberíamos mejorar?',
     'Please be specific. Critical feedback is particularly valuable to us.', 'Le pedimos que sea específico. Sus comentarios críticos son especialmente valiosos para nosotros.',
     'What should we change or do differently?', '¿Qué deberíamos cambiar o hacer de otra manera?'),
]
COPY = {
    'en': dict(title='Exam centre feedback',
        intro='Your feedback is essential to help us continuously improve. Please share your experience openly and honestly, including any areas where we could do better.',
        time='Approximately 2 minutes', scale='1 = Very poor | 10 = Excellent',
        conditional='What could we have done better?', required='Required', optional='Optional',
        submit='Submit feedback', cancel='Cancel', close='Close', submitting='Submitting…',
        submitted='Feedback form submitted', available='Available', unavailable='Available on exam date',
        open='Complete feedback ↗', missing='Please complete the highlighted required responses.',
        invalid_score='Select one rating from 1 to 10.', missing_comment='Please explain what we could have done better.',
        too_long='Please use no more than 10,000 characters.',
        expired='Feedback is only available on the exam date (GMT-3).',
        csrf='Security token expired. Please reload and try again.',
        locked='This feedback has already been submitted and cannot be edited.',
        thanks='Thank you for sharing your feedback.', error='Your feedback could not be submitted. Please try again.'),
    'es': dict(title='Evaluación del centro de examen',
        intro='Su opinión es fundamental para ayudarnos a mejorar continuamente. Comparta su experiencia con franqueza y honestidad, incluyendo los aspectos en los que podríamos mejorar.',
        time='Aproximadamente 2 minutos', scale='1 = Muy deficiente | 10 = Excelente',
        conditional='¿Qué podríamos haber hecho mejor?', required='Obligatorio', optional='Opcional',
        submit='Enviar evaluación', cancel='Cancelar', close='Cerrar', submitting='Enviando…',
        submitted='Evaluación enviada', available='Disponible', unavailable='Disponible el día del examen',
        open='Completar evaluación ↗', missing='Complete las respuestas obligatorias resaltadas.',
        invalid_score='Seleccione una calificación del 1 al 10.', missing_comment='Explique qué podríamos haber hecho mejor.',
        too_long='Utilice un máximo de 10.000 caracteres.',
        expired='La evaluación está disponible únicamente el día del examen (GMT-3).',
        csrf='La sesión de seguridad venció. Actualice la página e inténtelo nuevamente.',
        locked='Esta evaluación ya fue enviada y no puede editarse.',
        thanks='Gracias por compartir su opinión.', error='No se pudo enviar la evaluación. Inténtelo nuevamente.'),
}


def feedback_copy(language):
    language = 'es' if language == 'es' else 'en'
    spanish = language == 'es'
    return dict(COPY[language], questions=[dict(key=q[0], title=q[2 if spanish else 1], question=q[4 if spanish else 3]) for q in QUESTIONS],
                open_questions=[dict(key=q[0], title=q[2 if spanish else 1], description=q[4 if spanish else 3], placeholder=q[6 if spanish else 5]) for q in OPEN_QUESTIONS])
