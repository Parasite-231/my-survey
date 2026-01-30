package main

import (
	"database/sql"
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"os"
	"strings"
	"time"

	"github.com/gorilla/mux"
	_ "github.com/mattn/go-sqlite3"
	"github.com/rs/cors"
)

// SurveyResponse struct
type SurveyResponse struct {
	Q1              string   `json:"q1"`
	Q2              []string `json:"q2"`
	PortalRating    string   `json:"portal_rating"`
	LLMRating       string   `json:"llm_rating"`
	Q4              string   `json:"q4"`
	Q5              string   `json:"q5"`
	HasImprovements bool     `json:"has_improvements"`
	Improvements    string   `json:"improvements"`
	Timestamp       string   `json:"timestamp"`
}

func main() {
	// Initialize database
	initDB()

	// Create router
	r := mux.NewRouter()

	// Serve frontend
	r.PathPrefix("/").Handler(http.FileServer(http.Dir("../frontend/")))

	// API routes
	r.HandleFunc("/api/submit", submitSurvey).Methods("POST")
	r.HandleFunc("/api/responses", getResponses).Methods("GET")

	// CORS configuration
	c := cors.New(cors.Options{
		AllowedOrigins:   []string{"*"},
		AllowedMethods:   []string{"GET", "POST", "OPTIONS"},
		AllowedHeaders:   []string{"Content-Type"},
		AllowCredentials: true,
	})

	// Start server
	port := ":8080"
	if p := os.Getenv("PORT"); p != "" {
		port = ":" + p
	}

	fmt.Printf("Server starting on http://localhost%s\n", port)
	log.Fatal(http.ListenAndServe(port, c.Handler(r)))
}

func initDB() {
	// Create database file if it doesn't exist
	db, err := sql.Open("sqlite3", "./database.db")
	if err != nil {
		log.Fatal(err)
	}
	defer db.Close()

	// Create survey_responses table
	createTableSQL := `
	CREATE TABLE IF NOT EXISTS survey_responses (
		id INTEGER PRIMARY KEY AUTOINCREMENT,
		q1 TEXT,
		q2 TEXT,
		portal_rating TEXT,
		llm_rating TEXT,
		q4 TEXT,
		q5 TEXT,
		has_improvements INTEGER,
		improvements TEXT,
		timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
	);`

	_, err = db.Exec(createTableSQL)
	if err != nil {
		log.Fatal(err)
	}

	fmt.Println("Database initialized successfully")
}

func submitSurvey(w http.ResponseWriter, r *http.Request) {
	// Parse JSON request
	var response SurveyResponse
	err := json.NewDecoder(r.Body).Decode(&response)
	if err != nil {
		http.Error(w, "Invalid request body", http.StatusBadRequest)
		return
	}

	// Add timestamp
	response.Timestamp = time.Now().Format("2006-01-02 15:04:05")

	// Save to database
	db, err := sql.Open("sqlite3", "./database.db")
	if err != nil {
		http.Error(w, "Database error", http.StatusInternalServerError)
		return
	}
	defer db.Close()

	// Convert Q2 array to comma-separated string
	q2String := strings.Join(response.Q2, ",")

	// Insert response
	stmt, err := db.Prepare(`
		INSERT INTO survey_responses 
		(q1, q2, portal_rating, llm_rating, q4, q5, has_improvements, improvements, timestamp)
		VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
	`)
	if err != nil {
		http.Error(w, "Database error", http.StatusInternalServerError)
		return
	}
	defer stmt.Close()

	hasImprovements := 0
	if response.HasImprovements {
		hasImprovements = 1
	}

	_, err = stmt.Exec(
		response.Q1,
		q2String,
		response.PortalRating,
		response.LLMRating,
		response.Q4,
		response.Q5,
		hasImprovements,
		response.Improvements,
		response.Timestamp,
	)
	if err != nil {
		http.Error(w, "Failed to save response", http.StatusInternalServerError)
		return
	}

	// Send success response
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]string{
		"status":  "success",
		"message": "Survey response saved successfully",
	})
}

func getResponses(w http.ResponseWriter, r *http.Request) {
	db, err := sql.Open("sqlite3", "./database.db")
	if err != nil {
		http.Error(w, "Database error", http.StatusInternalServerError)
		return
	}
	defer db.Close()

	rows, err := db.Query("SELECT * FROM survey_responses ORDER BY timestamp DESC")
	if err != nil {
		http.Error(w, "Failed to fetch responses", http.StatusInternalServerError)
		return
	}
	defer rows.Close()

	var responses []map[string]interface{}
	for rows.Next() {
		var (
			id              int
			q1              string
			q2              string
			portalRating    sql.NullString
			llmRating       sql.NullString
			q4              string
			q5              string
			hasImprovements int
			improvements    sql.NullString
			timestamp       string
		)

		err := rows.Scan(&id, &q1, &q2, &portalRating, &llmRating, &q4, &q5, &hasImprovements, &improvements, &timestamp)
		if err != nil {
			continue
		}

		response := map[string]interface{}{
			"id":               id,
			"q1":               q1,
			"q2":               strings.Split(q2, ","),
			"portal_rating":    portalRating.String,
			"llm_rating":       llmRating.String,
			"q4":               q4,
			"q5":               q5,
			"has_improvements": hasImprovements == 1,
			"improvements":     improvements.String,
			"timestamp":        timestamp,
		}
		responses = append(responses, response)
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(responses)
}