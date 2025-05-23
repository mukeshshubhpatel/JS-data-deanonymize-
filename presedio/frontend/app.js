async function anonymize() {
  const text = document.getElementById('inputText').value;
  const names = document.getElementById('namesList').value
    .split(',')
    .map(s => s.trim())
    .filter(Boolean);

  const options = {
    name: document.getElementById('checkName').checked,
    date: document.getElementById('checkDate').checked,
    email: document.getElementById('checkEmail').checked,
    phone: document.getElementById('checkPhone').checked,
    id: document.getElementById('checkID').checked,
    address: document.getElementById('checkAddress').checked
  };

  try {
    const response = await axios.post('/anonymize', {
      raw_data: text,
      names_list: names,
      options: options
    });

    document.getElementById('outputText').textContent = response.data.anonymized;
  } catch (error) {
    document.getElementById('outputText').textContent = 'Error: ' + error.message;
    console.error('Anonymization failed:', error);
  }
}
