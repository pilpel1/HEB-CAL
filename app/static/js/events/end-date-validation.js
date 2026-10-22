// תאריך סיום לא לפני תאריך התחלה — משותף למודל ולטבלת האירועים

const END_DATE_BEFORE_START_MSG = 'תאריך הסיום לא יכול להיות לפני ההתחלה';

function isEndDateBeforeStart(startDate, endDate) {
    if (!startDate || !endDate) {
        return false;
    }
    // YYYY-MM-DD ניתן להשוות כמחרוזת
    return endDate < startDate;
}

function syncEndDateMin(startDate, endInput) {
    if (!endInput) {
        return;
    }
    if (startDate) {
        // min של input[type=date] מאפיר וחוסם בחירה של תאריכים מוקדמים יותר בלוח של הדפדפן
        endInput.setAttribute('min', startDate);
        if (endInput.value && endInput.value < startDate) {
            endInput.value = '';
        }
        endInput.setCustomValidity(
            endInput.value && endInput.value < startDate ? END_DATE_BEFORE_START_MSG : ''
        );
    } else {
        endInput.removeAttribute('min');
        endInput.setCustomValidity('');
    }
}

function assertEndDateNotBeforeStart(startDate, endDate, endInput = null) {
    if (!isEndDateBeforeStart(startDate, endDate)) {
        if (endInput) {
            endInput.setCustomValidity('');
        }
        return true;
    }
    if (endInput) {
        endInput.setCustomValidity(END_DATE_BEFORE_START_MSG);
        endInput.reportValidity();
        return false;
    }
    alert(END_DATE_BEFORE_START_MSG);
    return false;
}
