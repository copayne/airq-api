# Hudson Air Quality API

## About
The Hudson Air Quality API is a simple flask server built to store and serve air quality sensor readings to the Hudson Air Quality App. It uses a graphql endpoint to process data for the end user, with a postgres database. The purpose is to have both historical and live data in order to maximize air quality throughout 937 Hudson.


## Initialize API on a new machine

## Create Database
Install postgres

```sudo apt-get install postgresql```

Enter postgres and create database
```
sudo -u postgres psql
CREATE DATABASE sensor_readings;
```

If needed, updated password for db user
```
ALTER USER postgres WITH PASSWORD {{new_password}};
```
Exit postgres

```\q```


## Setup API
### Setup SSH key with github on machine
Run ```ssh-keygen``` on machine

Navigate to file (/.ssh by default)

Run ```cat id_rsa.pub``` and copy contents

Create new key under settings/SSH and GPG Keys

Copy contens to github key and save

### Clone repository on machine
```git clone git@github.com:copayne/airq-api.git```

### Create virtual environment
Ensure python3 is installed

```
sudo apt-get update
sudo apt-get install python3 python3-pip
```

Install virtualenv

```pip install virtualenv```

Navigate to app folder and create environment
```
python3 -m venv {{env_name}}
source {{env_name}/bin/activate
```

### Install dependencies
```pip install -r requirements.txt```

### Initialize database
Run the following command to initialize the database

```python3 init_db.py```

(Optional) Run dummy data script to see database

```python3 db-dummy-data.py```

### Start app
```python3 run.py```

### Check status
- Open browser and navigate to http://127.0.0.1/graphql
- Should open to graphql utility tool.