# forum-user-service

# Installating dependencies
```
pip install -r requriements.txt

# Running
While in the root folder of the project (see [here](https://github.com/ZephyrusLiu/GroupProject))
```
python -m forum-user-service.src.main
```

# Importing User Service Database
Run the following: `mysql -u {user} -p {db_name} < user_db.sql`

Where **user** is your database username and **db_name** is the name you want for the database.

eg: `mysql -u my_user -p my_db < user_db.sql`
