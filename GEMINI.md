# GEMINI.md

## Project Overview

This is a React-based web application called "Lumina AI Retouch" for intelligent photo retouching. The application allows users to upload an image, and then it analyzes the image and suggests edits. Users can apply edits, including generative changes and adjustments.

The project is built with the following technologies:

*   **Frontend:** React, Vite, TypeScript
*   **UI:** Framer Motion, Heroicons
*   **Backend:** Gemini API (currently mocked)

The application features a modern and interactive UI with features like drag-and-drop, theme toggling, and animations.

## Building and Running

To build and run the project, follow these steps:

1.  **Install dependencies:**
    ```bash
    npm install
    ```
2.  **Set the `GEMINI_API_KEY`:**
    Create a `.env.local` file in the root of the project and add the following line:
    ```
    GEMINI_API_KEY=your_api_key
    ```
3.  **Run the development server:**
    ```bash
    npm run dev
    ```
4.  **Build for production:**
    ```bash
    npm run build
    ```
5.  **Preview the production build:**
    ```bash
    npm run preview
    ```

## Development Conventions

*   **Styling:** The project uses Tailwind CSS for styling.
*   **Components:** The UI is built with React components, which are located in the `src/components` directory.
*   **Services:** The application's services, such as the one for interacting with the Gemini API, are located in the `src/services` directory.
*   **State Management:** The application uses React's built-in state management features.
*   **Linting and Formatting:** The project is set up with ESLint and Prettier to enforce a consistent coding style.
