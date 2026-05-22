
<?php
// index.php (Public-safe example)
// Place inside: yourdomain.com/api/

header("Access-Control-Allow-Origin: *");
header("Content-Type: application/json");

if ($_SERVER["REQUEST_METHOD"] !== "POST") {
    http_response_code(405);
    echo json_encode([
        "error" => "Only POST requests allowed."
    ]);
    exit;
}

$data = json_decode(file_get_contents("php://input"), true);

if (!$data || !isset($data["action"])) {
    http_response_code(400);
    echo json_encode([
        "error" => "Missing required parameter: action"
    ]);
    exit;
}

$action = $data["action"];

$text = $data["text"] ?? "";
$query = $data["query"] ?? "";
$image = $data["b64_image"] ?? "";

if (!$text && !$image) {
    http_response_code(400);
    echo json_encode([
        "error" => "Provide text or image input"
    ]);
    exit;
}

/*
|--------------------------------------------------------------------------
| Prevent extremely large payloads
|--------------------------------------------------------------------------
*/
if (strlen($text) > 6000) {
    $text = substr($text, 0, 6000)
          . "\n...[Content truncated]";
}

/*
|--------------------------------------------------------------------------
| Secure config (store real values in .env or server config)
|--------------------------------------------------------------------------
*/
$API_KEY = getenv("AI_API_KEY");
$MODEL   = getenv("AI_MODEL") ?: "default-model";

if (!$API_KEY) {
    http_response_code(500);
    echo json_encode([
        "error" => "Server configuration missing"
    ]);
    exit;
}

/*
|--------------------------------------------------------------------------
| System Prompt
|--------------------------------------------------------------------------
*/
$system_prompt =
"You are an educational assistant.
Explain difficult material simply.
Use bullets, headings, and short examples.";

/*
|--------------------------------------------------------------------------
| User Prompt by action
|--------------------------------------------------------------------------
*/
switch ($action) {

    case "summary":
        $prompt =
        "Summarize this material for a student:\n\n"
        . $text;
        break;

    case "quiz":
        $prompt =
        "Generate 5 MCQs from:\n\n"
        . $text;
        break;

    case "ask":
        $prompt =
        "Context:\n"
        . $text .
        "\n\nQuestion:\n"
        . $query;
        break;

    default:
        http_response_code(400);
        echo json_encode([
            "error" => "Invalid action"
        ]);
        exit;
}

/*
|--------------------------------------------------------------------------
| Support optional image input
|--------------------------------------------------------------------------
*/
$user_content = $prompt;

if (!empty($image)) {
    $user_content = [
        [
            "type"=>"text",
            "text"=>$prompt
        ],
        [
            "type"=>"image_url",
            "image_url"=>[
                "url"=>"data:image/jpeg;base64,".$image
            ]
        ]
    ];
}

/*
|--------------------------------------------------------------------------
| Generic AI payload
|--------------------------------------------------------------------------
*/
$payload = [

    "model" => $MODEL,

    "messages" => [

        [
            "role"=>"system",
            "content"=>$system_prompt
        ],

        [
            "role"=>"user",
            "content"=>$user_content
        ]

    ],

    "temperature"=>0.3,
    "max_tokens"=>1500
];

/*
|--------------------------------------------------------------------------
| API Request
|--------------------------------------------------------------------------
*/
$ch = curl_init("https://your-ai-endpoint.com/chat");

curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
curl_setopt($ch, CURLOPT_POST, true);
curl_setopt($ch, CURLOPT_POSTFIELDS, json_encode($payload));

curl_setopt($ch, CURLOPT_HTTPHEADER, [

    "Authorization: Bearer ".$API_KEY,
    "Content-Type: application/json"

]);

$response = curl_exec($ch);

if (curl_errno($ch)) {

    http_response_code(500);

    echo json_encode([
        "error"=>"Connection failed"
    ]);

    curl_close($ch);
    exit;
}

$status = curl_getinfo($ch, CURLINFO_HTTP_CODE);

curl_close($ch);

$result = json_decode($response, true);

/*
|--------------------------------------------------------------------------
| Response Handling
|--------------------------------------------------------------------------
*/
if ($status !== 200) {

    http_response_code($status);

    echo json_encode([
        "error"=>"AI service error",
        "details"=>$result
    ]);

    exit;
}

echo json_encode([

    "response" =>
    $result["choices"][0]["message"]["content"]
    ?? "No response"

]);
