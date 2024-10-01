const form = document.querySelector('form');
const message = document.getElementById('message');
const smallMessage = document.getElementById('smallMessage');
const urlMessage = 'Type the URL of the product';
const emailMessage = 'Enter your Email address';
const url = document.getElementById('url');
const email = document.getElementById('Email');
const submitBtn = document.getElementById('submit');

function validateEmail(email) {
    const re = /^(([^<>()\[\]\\.,;:\s@"]+(\.[^<>()\[\]\\.,;:\s@"]+)*)|(".+"))@((\[[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}])|(([a-zA-Z\-0-9]+\.)+[a-zA-Z]{2,}))$/;
    return re.test(String(email).toLowerCase());
}

function validateURL(url) {
    const re = /^(https?:\/\/)?(www\.)?ebay\.com\/.*$/;
    return re.test(url);
}

function formValidation(){
    submitBtn.addEventListener('click', function(event){
        event.preventDefault();

        if (!validateURL(url.value)) {
            smallMessage.innerHTML = "Please enter a valid eBay URL";
            return;
        }

        if (!validateEmail(email.value)) {
            smallMessage.innerHTML = "Please enter a valid email address";
            return;
        }

        apiUrl=`${baseUrl}?url=$${encodeURIComponent(url.value)}&email=$${encodeURIComponent(email.value)}`;
        // Disable the submit button and show loading message
        submitBtn.disabled = true;
        message.innerHTML = "Submitting...";
        
        fetch(apiUrl, {
            method: 'POST',
        })
        .then(response => {
            if (!response.ok) {
                throw new Error('Network response was not ok');
            }
            return response.json();
        })
        .then(data => {
            form.innerHTML = '<h1>Good job!</h1><p class="success-message">There is a confirmation link waiting in your email inbox.</p>';
            document.body.style.background = '#D7F5DE';
        })
        .catch(error => {
            console.error('Error:', error);
            message.innerHTML = "An error occurred. Please try again later.";
            smallMessage.innerHTML = error.message;
            document.body.style.background = '#FFCCCB';
        })
        .finally(() => {
            submitBtn.disabled = false;
        });
    });
}

formValidation();