IMPROVEMENTS

### Global Configs:

- Add other global settings might be useful (e.g., date/time formats, default report output formats).
- Allow global config changes to certain things for user to customize their experience.
- When units of measurement added to a goal, add to a list of acceptable measurement units if it's not one that already exists. Start with basic units of measure already in config fie.
- Expand global defaults as needed to apply throughout other modules (aka tags)
- Add function to set or update aliases. This is important for the "Low Friction Usability Framework."
- function to set or update aliases. This is important for the "Low Friction Usability Framework."
- Improve error handling around saving and loading mechanisms.

### Paths:

- Have a way for users to set these paths through a CLI command or environment variable for more flexibility.
- Have a way for users to define aliases within the CLI, which would update this section of the config.

### Cron:

- Add more general scheduling mechanism might be useful for other modules in the future.

### Error Handling:

- What happens if the TOML file is malformed? There should be more robust error handling to provide informative messages to the user.

### Tracker Module:

- It assumes that all entries are numeric for goal tracking. This might not be correct for boolean or string types.
