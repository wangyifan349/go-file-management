# Go File Management System 🗂️

A simple multi-user file management web application written in Go.  
This project demonstrates a basic file management system with registration, login, and file operations through a web interface.

---

## Features ✨

- User registration and login with username and password 🔐
- Personal isolated file storage for each user 📁
- Upload, download, rename, move, and delete files and directories 📤📥
- Clean and minimal web UI for ease of use 💻
- Built-in SQLite3 for user account storage 🗄️

---

## Getting Started 🚀

### Prerequisites

- [Go Programming Language](https://golang.org/doc/install) (version 1.16 or above recommended)
- Git (to clone this repository)

Check your Go installation by running:

```bash
go version
```

Make sure it outputs a Go version >=1.16.

### Installation

1. Clone this repository:

   ```bash
   git clone https://github.com/wangyifan349/go-file-management.git
   cd go-file-management
   ```

2. Build the application:

   ```bash
   go build -o filemanager main.go
   ```

3. Run the server:

   ```bash
   ./filemanager
   ```

4. Open your web browser and navigate to:

   ```
   http://localhost:8080/login
   ```

5. Register a new account and start managing your files!

---

## Configuration ⚙️

The following constants can be modified in `main.go` to customize behavior:

- `listenAddr` (default `:8080`): Server listening address and port.
- `baseDir` (default `./userfiles`): Directory where user files are stored.
- `dbFile` (default `./users.db`): SQLite database file path.

Modify and rebuild to apply changes.

---

## Project Structure 📁

- `main.go` – Main source code file containing server and handlers.
- `users.db` – SQLite database created on first run for user data.
- `userfiles/` – Root folder created dynamically storing user data directories.

---

## Dependencies 📦

- [Go SQLite3 driver](https://github.com/mattn/go-sqlite3)
- Go standard library packages such as `net/http`, `os`, `io`, `encoding/json`, `database/sql`

To install the SQLite3 driver, use:

```bash
go get github.com/mattn/go-sqlite3
```

---

## Security Considerations 🔒

- This demo stores passwords in plaintext — **do not deploy as-is to production!**
- Use a secure password hashing algorithm such as [bcrypt](https://pkg.go.dev/golang.org/x/crypto/bcrypt) in real-world scenarios.
- Add HTTPS support for encrypted communication.
- Apply user input sanitization and validation on client and server side.
- Consider adding session management instead of cookie-only authentication.

---

## Contributing 🤝

Pull requests, issues, and suggestions are welcome!  
Please follow Go coding conventions and write clear commit messages.

---

## License 📄

This project is licensed under the MIT License. See `LICENSE` file for details.

---

## About Go 🤓

Go (Golang) is an open-source programming language designed by Google. It is statically typed, compiled, and well suited for building scalable web servers and services.  

Learn more and download Go at the official site: [https://golang.org](https://golang.org)

---

## Contact ✉️

Created and maintained by [wangyifan349](https://github.com/wangyifan349)  
Feel free to connect!

