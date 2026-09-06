Always use strong typing and check it with pyright after evolutions/corrections to reduce runtine errors.
No pyright warning or error is allowed, fix them before considering the build is over.
Keep cognitive complexity equal or below 15 so that no Sonarqube issues are created.
For any DB structure changes, propose to run a one shot SQL script manually instead of generating python code.
