package main

import (
	"database/sql"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"os"
	"path/filepath"
	"strings"

	_ "github.com/mattn/go-sqlite3"
)

var (
	baseDir    = "./userfiles" // Base directory for storing user files
	db         *sql.DB
	dbFile     = "./users.db"  // SQLite database file
	listenAddr = ":8080"       // Listening address for the server
)

func main() {
	os.MkdirAll(baseDir, 0755)
	initDatabase()

	http.HandleFunc("/", rootHandler)
	http.HandleFunc("/login", loginPageHandler)
	http.HandleFunc("/api/login", loginHandler)
	http.HandleFunc("/api/register", registerHandler)

	http.HandleFunc("/files/", filesHandler)
	http.HandleFunc("/upload", uploadHandler)
	http.HandleFunc("/download/", downloadHandler)
	http.HandleFunc("/delete", deleteHandler)
	http.HandleFunc("/mkdir", mkdirHandler)
	http.HandleFunc("/rename", renameHandler)
	http.HandleFunc("/move", moveHandler)

	fmt.Println("Server started at " + listenAddr)
	log.Fatal(http.ListenAndServe(listenAddr, nil))
}

// initDatabase initializes the user database and creates the users table if it doesn't exist.
func initDatabase() {
	var err error
	db, err = sql.Open("sqlite3", dbFile)
	if err != nil {
		log.Fatal("Failed to open database:", err)
	}
	createTableSql := `
	CREATE TABLE IF NOT EXISTS users (
		id INTEGER PRIMARY KEY AUTOINCREMENT,
		userName TEXT UNIQUE NOT NULL,
		password TEXT NOT NULL
	);`
	if _, err := db.Exec(createTableSql); err != nil {
		log.Fatal("Failed to create users table:", err)
	}
}

// loginPageHandler serves the login and registration HTML page.
func loginPageHandler(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "text/html; charset=utf-8")
	html := getLoginPageHTML()
	_, _ = w.Write([]byte(html))
}

// loginHandler processes login POST requests.
func loginHandler(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "Only POST method is allowed", http.StatusMethodNotAllowed)
		return
	}
	userName := r.FormValue("username")
	password := r.FormValue("password")
	if userName == "" || password == "" {
		jsonError(w, "Username and password cannot be empty")
		return
	}
	var dbPassword string
	err := db.QueryRow("SELECT password FROM users WHERE userName=?", userName).Scan(&dbPassword)
	if err != nil || dbPassword != password {
		jsonError(w, "Invalid username or password")
		return
	}
	http.SetCookie(w, &http.Cookie{Name: "username", Value: userName, Path: "/"})
	jsonResponse(w, map[string]interface{}{"success": true, "msg": "Login successful"})
}

// registerHandler processes user registration POST requests.
func registerHandler(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "Only POST method is allowed", http.StatusMethodNotAllowed)
		return
	}
	userName := r.FormValue("username")
	password := r.FormValue("password")
	if userName == "" || password == "" {
		jsonError(w, "Username and password cannot be empty")
		return
	}
	if strings.ContainsAny(userName, `/\`) {
		jsonError(w, "Username contains invalid characters")
		return
	}
	_, err := db.Exec("INSERT INTO users(userName,password) VALUES(?,?)", userName, password)
	if err != nil {
		jsonError(w, "Username already exists")
		return
	}
	userRootPath := filepath.Join(baseDir, userName)
	os.MkdirAll(userRootPath, 0755)
	jsonResponse(w, map[string]interface{}{"success": true, "msg": "Registration successful"})
}

// rootHandler serves the main file management page after successful login.
func rootHandler(w http.ResponseWriter, r *http.Request) {
	userName, err := getUserName(w, r)
	if err != nil {
		return
	}
	w.Header().Set("Content-Type", "text/html; charset=utf-8")
	html := getFileManagerPageHTML(userName)
	_, _ = w.Write([]byte(html))
}

// getUserName retrieves the username from the cookie or redirects to the login page if the cookie is missing.
func getUserName(w http.ResponseWriter, r *http.Request) (string, error) {
	cookie, err := r.Cookie("username")
	if err != nil || cookie.Value == "" {
		http.Redirect(w, r, "/login", http.StatusSeeOther)
		return "", fmt.Errorf("user not logged in")
	}
	return cookie.Value, nil
}

// filesHandler provides a JSON response containing the list of files in the requested user directory.
func filesHandler(w http.ResponseWriter, r *http.Request) {
	userName, relativePath, err := parseUserPath(r)
	if err != nil {
		http.Error(w, "Invalid path", http.StatusBadRequest)
		return
	}
	userRootPath := filepath.Join(baseDir, userName)
	absolutePath := filepath.Join(userRootPath, relativePath)

	info, err := os.Stat(absolutePath)
	if err != nil || !info.IsDir() {
		http.Error(w, "Directory not found", http.StatusNotFound)
		return
	}

	entries, err := os.ReadDir(absolutePath)
	if err != nil {
		http.Error(w, "Failed to read directory", http.StatusInternalServerError)
		return
	}

	type fileEntry struct {
		Name  string `json:"name"`
		IsDir bool   `json:"isDir"`
	}
	var fileList []fileEntry

	for _, entry := range entries {
		fileList = append(fileList, fileEntry{Name: entry.Name(), IsDir: entry.IsDir()})
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]interface{}{"success": true, "files": fileList})
}

// uploadHandler allows users to upload files to their directory.
func uploadHandler(w http.ResponseWriter, r *http.Request) {
	userName, err := getUserName(w, r)
	if err != nil {
		return
	}
	path := r.URL.Query().Get("path")
	userRootPath := filepath.Join(baseDir, userName)
	destDirectory := filepath.Join(userRootPath, path)
	if !strings.HasPrefix(destDirectory, userRootPath) {
		http.Error(w, "Invalid path", http.StatusBadRequest)
		return
	}
	info, err := os.Stat(destDirectory)
	if err != nil || !info.IsDir() {
		http.Error(w, "Upload directory does not exist", http.StatusBadRequest)
		return
	}
	file, header, err := r.FormFile("file")
	if err != nil {
		http.Error(w, "Upload failed", http.StatusBadRequest)
		return
	}
	defer file.Close()

	if strings.ContainsAny(header.Filename, `/\`) {
		http.Error(w, "Invalid filename", http.StatusBadRequest)
		return
	}

	destFilePath := filepath.Join(destDirectory, header.Filename)
	destFile, err := os.Create(destFilePath)
	if err != nil {
		http.Error(w, "Failed to save file", http.StatusInternalServerError)
		return
	}
	defer destFile.Close()

	_, err = io.Copy(destFile, file)
	if err != nil {
		http.Error(w, "Failed to save file", http.StatusInternalServerError)
		return
	}
	jsonResponse(w, map[string]interface{}{"success": true, "msg": "Upload successful"})
}

// downloadHandler enables users to download files.
func downloadHandler(w http.ResponseWriter, r *http.Request) {
	parts := strings.Split(strings.TrimPrefix(r.URL.Path, "/download/"), "/")
	if len(parts) < 2 {
		http.Error(w, "Invalid parameters", http.StatusBadRequest)
		return
	}
	userName := parts[0]
	relativePath := filepath.Join(parts[1:]...)
	userRootPath := filepath.Join(baseDir, userName)
	absolutePath := filepath.Join(userRootPath, relativePath)

	info, err := os.Stat(absolutePath)
	if err != nil || info.IsDir() {
		http.Error(w, "File not found", http.StatusNotFound)
		return
	}
	w.Header().Set("Content-Disposition", "attachment; filename="+info.Name())
	w.Header().Set("Content-Type", "application/octet-stream")
	http.ServeFile(w, r, absolutePath)
}

// deleteHandler deletes a file or an empty directory.
func deleteHandler(w http.ResponseWriter, r *http.Request) {
	userName, err := getUserName(w, r)
	if err != nil {
		return
	}
	path := r.FormValue("path")
	if path == "" {
		http.Error(w, "Missing path parameter", http.StatusBadRequest)
		return
	}
	userRootPath := filepath.Join(baseDir, userName)
	absolutePath := filepath.Join(userRootPath, path)
	if !strings.HasPrefix(absolutePath, userRootPath) {
		http.Error(w, "Invalid path", http.StatusBadRequest)
		return
	}

	info, err := os.Stat(absolutePath)
	if err != nil {
		http.Error(w, "File not found", http.StatusNotFound)
		return
	}

	err = os.Remove(absolutePath)
	if err != nil {
		http.Error(w, "Deletion failed; directory must be empty", http.StatusBadRequest)
		return
	}
	jsonResponse(w, map[string]interface{}{"success": true, "msg": "Deletion successful"})
}

// mkdirHandler creates a new directory.
func mkdirHandler(w http.ResponseWriter, r *http.Request) {
	userName, err := getUserName(w, r)
	if err != nil {
		return
	}
	parentPath := r.FormValue("path")
	dirName := r.FormValue("name")

	if dirName == "" || strings.ContainsAny(dirName, `/\`) {
		http.Error(w, "Invalid directory name", http.StatusBadRequest)
		return
	}

	userRootPath := filepath.Join(baseDir, userName)
	absoluteParentPath := filepath.Join(userRootPath, parentPath)
	if !strings.HasPrefix(absoluteParentPath, userRootPath) {
		http.Error(w, "Invalid path", http.StatusBadRequest)
		return
	}

	newDirectoryPath := filepath.Join(absoluteParentPath, dirName)
	err = os.Mkdir(newDirectoryPath, 0755)
	if err != nil {
		http.Error(w, "Failed to create directory", http.StatusInternalServerError)
		return
	}
	jsonResponse(w, map[string]interface{}{"success": true, "msg": "Directory created successfully"})
}

// renameHandler renames a file or a directory.
func renameHandler(w http.ResponseWriter, r *http.Request) {
	userName, err := getUserName(w, r)
	if err != nil {
		return
	}
	oldName := r.FormValue("path")
	newName := r.FormValue("newname")
	if newName == "" || strings.ContainsAny(newName, `/\`) {
		http.Error(w, "Invalid new name", http.StatusBadRequest)
		return
	}

	userRootPath := filepath.Join(baseDir, userName)
	absoluteOldPath := filepath.Join(userRootPath, oldName)
	if !strings.HasPrefix(absoluteOldPath, userRootPath) {
		http.Error(w, "Invalid path", http.StatusBadRequest)
		return
	}

	if _, err := os.Stat(absoluteOldPath); err != nil {
		http.Error(w, "Original path does not exist", http.StatusBadRequest)
		return
	}

	newPath := filepath.Join(filepath.Dir(absoluteOldPath), newName)
	if _, err := os.Stat(newPath); err == nil {
		http.Error(w, "New name already exists", http.StatusBadRequest)
		return
	}

	err = os.Rename(absoluteOldPath, newPath)
	if err != nil {
		http.Error(w, "Renaming failed", http.StatusInternalServerError)
		return
	}
	jsonResponse(w, map[string]interface{}{"success": true, "msg": "Renaming successful"})
}

// moveHandler moves a file or a directory to a new location.
func moveHandler(w http.ResponseWriter, r *http.Request) {
	userName, err := getUserName(w, r)
	if err != nil {
		return
	}
	oldPath := r.FormValue("path")
	newDestination := r.FormValue("newpath")

	if oldPath == "" || newDestination == "" {
		http.Error(w, "Missing parameters", http.StatusBadRequest)
		return
	}

	userRootPath := filepath.Join(baseDir, userName)
	absoluteOldPath := filepath.Join(userRootPath, oldPath)
	absoluteNewDir := filepath.Join(userRootPath, newDestination)

	if !strings.HasPrefix(absoluteOldPath, userRootPath) || !strings.HasPrefix(absoluteNewDir, userRootPath) {
		http.Error(w, "Invalid path", http.StatusBadRequest)
		return
	}

	if _, err := os.Stat(absoluteOldPath); err != nil {
		http.Error(w, "Source file not found", http.StatusBadRequest)
		return
	}

	info, err := os.Stat(absoluteNewDir)
	if err != nil || !info.IsDir() {
		http.Error(w, "Destination directory not found", http.StatusBadRequest)
		return
	}

	destinationPath := filepath.Join(absoluteNewDir, filepath.Base(absoluteOldPath))
	err = os.Rename(absoluteOldPath, destinationPath)
	if err != nil {
		http.Error(w, "Moving failed", http.StatusInternalServerError)
		return
	}
	jsonResponse(w, map[string]interface{}{"success": true, "msg": "Move successful"})
}

// parseUserPath extracts the username and the relative path from the URL path /files/<username>/<relpath>
func parseUserPath(r *http.Request) (string, string, error) {
	trimmedPath := strings.TrimPrefix(r.URL.Path, "/files/")
	parts := strings.Split(trimmedPath, "/")
	if len(parts) < 1 {
		return "", "", fmt.Errorf("path parsing error")
	}
	userName := parts[0]
	if userName == "" || strings.ContainsAny(userName, `/\`) {
		return "", "", fmt.Errorf("invalid username")
	}
	var relPath string
	if len(parts) > 1 {
		relPath = filepath.Join(parts[1:]...)
	} else {
		relPath = ""
	}
	return userName, relPath, nil
}

// jsonError sends a JSON error response with the specified message.
func jsonError(w http.ResponseWriter, msg string) {
	w.Header().Set("Content-Type", "application/json")
	w.Write([]byte(fmt.Sprintf(`{"success":false,"msg":"%s"}`, msg)))
}

// jsonResponse sends a JSON response with the specified data.
func jsonResponse(w http.ResponseWriter, data map[string]interface{}) {
	jsonData, _ := json.Marshal(data)
	w.Header().Set("Content-Type", "application/json")
	w.Write(jsonData)
}

// getLoginPageHTML provides the HTML content for the login and registration page.
func getLoginPageHTML() string {
	return `
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<title>Login & Registration - File Management</title>
<style>
body{font-family:sans-serif; background:#eef2f3; padding:20px;}
form{margin:20px auto; width:300px; padding:15px; background:#fff; border-radius: 5px;}
input[type=text],input[type=password] {width:100%; padding:8px; margin:8px 0; box-sizing: border-box;}
button{width:100%; padding:10px; margin:8px 0; background:#2f6f2f; color:#fff; border:none; cursor:pointer; font-size:16px;}
button:hover{background:#245d24;}
#errorMsg{color:red; margin-bottom:10px;}
h2{color:#2f6f2f;}
</style>
</head>
<body>
<h2>Login</h2>
<div id="errorMsg"></div>
<form id="loginForm">
<input type="text" name="username" placeholder="Username" required />
<input type="password" name="password" placeholder="Password" required />
<button type="submit">Login</button>
</form>

<h2>Register</h2>
<form id="registerForm">
<input type="text" name="username" placeholder="Username" required />
<input type="password" name="password" placeholder="Password" required />
<button type="submit">Register</button>
</form>

<script>
const errorDiv = document.getElementById("errorMsg");
document.getElementById("loginForm").onsubmit = async function(e){
	e.preventDefault();
	errorDiv.innerText = "";
	let form = e.target;
	let fd = new FormData(form);
	let res = await fetch("/api/login", {method:"POST", body: fd});
	let data = await res.json();
	if(data.success){
		location.href="/";
	} else {
		errorDiv.innerText = data.msg;
	}
};
document.getElementById("registerForm").onsubmit = async function(e){
	e.preventDefault();
	errorDiv.innerText = "";
	let form = e.target;
	let fd = new FormData(form);
	let res = await fetch("/api/register", {method:"POST", body: fd});
	let data = await res.json();
	if(data.success){
		alert("Registration successful, please login");
		form.reset();
	} else {
		errorDiv.innerText = data.msg;
	}
};
</script>
</body>
</html>
`
}

// getFileManagerPageHTML returns the main file manager page HTML content with the provided userName.
func getFileManagerPageHTML(userName string) string {
	page := `
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<title>File Management System</title>
<style>
body{font-family:sans-serif; background:#e0f0e0; margin: 0; padding: 0;}
#top {padding: 10px; background:#2f6f2f; color: #fff;}
#filelist {padding: 10px;}
.item {padding: 5px; margin: 3px 0; background: #fff; border-radius: 3px; cursor: pointer; user-select:none;}
.item:hover {background: #dbf0db;}
.item .name {display:inline-block; width: 60%;}
.item .actions {display:inline-block; width: 35%; text-align:right;}
button {margin-left:5px;}
.dir {font-weight:bold; color: #2f6f2f;}
</style>
</head>
<body>
<div id="top">
    User: <span id="userName">%s</span>
    <button onclick="logout()">Logout</button>
    <button onclick="goUp()">Up One Level</button>
    <button onclick="makeDirectory()">New Folder</button>
    <input type="file" id="fileUpload" />
    <button onclick="uploadFile()">Upload File</button>
    <span id="pathDisplay"></span>
</div>
<div id="fileList"></div>

<script>
let userName = "%s";
let currentPath = "";

function apiFetch(url, options) {
    return fetch(url, options).then(r => r.json());
}

function logout() {
    document.cookie = "username=;path=/;max-age=0";
    window.location.href = "/login";
}

function goUp() {
    if(currentPath === "") return;
    let parts = currentPath.split("/");
    parts.pop();
    currentPath = parts.join("/");
    loadFiles();
}

function loadFiles() {
    document.getElementById("pathDisplay").innerText = "Path: /" + currentPath;
    fetch("/files/" + userName + "/" + currentPath).then(r=>r.json()).then(data=>{
        if(!data.success) {
            alert("Failed to load files.");
            return;
        }
        let div = document.getElementById("fileList");
        div.innerHTML = "";
        data.files.forEach(item=>{
            let ele = document.createElement("div");
            ele.className = "item";
            ele.innerHTML = '<span class="name '+(item.isDir ? 'dir':'')+'">'+item.name+'</span>' +
                '<span class="actions">' +
                (item.isDir ? '<button onclick="openDirectory(event,\''+item.name+'\')">Open</button>': '') +
                '<button onclick="downloadFile(event,\''+item.name+'\')">Download</button>'+
                '<button onclick="renameItem(event,\''+item.name+'\')">Rename</button>'+
                '<button onclick="deleteItem(event,\''+item.name+'\')">Delete</button>'+
                '<button onclick="moveItem(event,\''+item.name+'\')">Move</button>'+
                '</span>';
            div.appendChild(ele);
        });
    });
}

function openDirectory(e, name) {
    e.stopPropagation();
    currentPath = currentPath ? currentPath + "/" + name : name;
    loadFiles();
}

function downloadFile(e, name) {
    e.stopPropagation();
    let path = currentPath ? currentPath + "/" + name : name;
    window.open("/download/" + userName + "/" + path, "_blank");
}

function renameItem(e, oldName) {
    e.stopPropagation();
    let newName = prompt("New name", oldName);
    if(!newName || newName === oldName) return;
    let path = currentPath ? currentPath + "/" + oldName : oldName;
    fetch("/rename", {
        method: "POST",
        headers: {'Content-Type':'application/x-www-form-urlencoded'},
        body: "path="+encodeURIComponent(path)+"&newname="+encodeURIComponent(newName)
    }).then(r=>r.json()).then(res=>{
        if(res.success) loadFiles();
        else alert("Failed: "+res.msg);
    });
}

function deleteItem(e, name) {
    e.stopPropagation();
    if(!confirm("Confirm delete "+name+"?")) return;
    let path = currentPath ? currentPath + "/" + name : name;
    fetch("/delete", {
        method: "POST",
        headers: {'Content-Type':'application/x-www-form-urlencoded'},
        body: "path="+encodeURIComponent(path)
    }).then(r=>r.json()).then(res=>{
        if(res.success) loadFiles();
        else alert("Failed: "+res.msg);
    });
}

function makeDirectory() {
    let name = prompt("New folder name");
    if(!name) return;
    fetch("/mkdir", {
        method: "POST",
        headers: {'Content-Type':'application/x-www-form-urlencoded'},
        body: "path="+encodeURIComponent(currentPath)+"&name="+encodeURIComponent(name)
    }).then(r=>r.json()).then(res=>{
        if(res.success) loadFiles();
        else alert("Failed: "+res.msg);
    });
}

function uploadFile() {
    let fileInput = document.getElementById("fileUpload");
    let file = fileInput.files[0];
    if(!file) {
        alert("Please select a file");
        return;
    }
    let formData = new FormData();
    formData.append("file", file);
    fetch("/upload?path="+encodeURIComponent(currentPath), {
        method: "POST",
        body: formData
    }).then(r=>r.json()).then(res=>{
        if(res.success) loadFiles();
        else alert("Failed: "+res.msg);
    });
}

function moveItem(e, name) {
    e.stopPropagation();
    let newPath = prompt("Enter destination folder relative path");
    if(newPath === null) return;
    let oldPath = currentPath ? currentPath + "/" + name : name;
    fetch("/move", {
        method: "POST",
        headers: {'Content-Type':'application/x-www-form-urlencoded'},
        body: "path="+encodeURIComponent(oldPath)+"&newpath="+encodeURIComponent(newPath)
    }).then(r=>r.json()).then(res=>{
        if(res.success) loadFiles();
        else alert("Failed: "+res.msg);
    });
}

window.onload = loadFiles;
</script>
</body></html>
`
	return fmt.Sprintf(page, userName, userName)
}
