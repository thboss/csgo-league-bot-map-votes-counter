FROM python:3.6-slim

# install required packages
RUN apt-get update && apt-get upgrade -y && apt-get install -y \
	libpq-dev \
	postgresql-client \
	gcc

# create folder for application, copy application, and set directory at application
RUN mkdir /PugBot
COPY / /PugBot/
WORKDIR /PugBot/

# install python packages 
RUN pip3 install -r requirements.txt

# copy .env file
COPY /DockerBotConfig /PugBot/.env

# apply yoyo migrations and launch application
CMD python3 migrate.py up && python3 launcher.py