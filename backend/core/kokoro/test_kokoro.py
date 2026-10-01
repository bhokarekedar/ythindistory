import soundfile as sf
import os
from kokoro import KPipeline

def main():
    print("Initializing Kokoro pipeline for American English (lang_code='a')...")
    try:
        pipeline = KPipeline(lang_code='a')
    except Exception as e:
        print(f"Error initializing pipeline: {e}")
        return

    # A 30-second English thriller movie recap script
    text = (
        "The story begins with a man whose life changes completely in an instant. "
        "One night, he finds a mysterious girl on the street asking for his help. "
        "He brings her home, completely unaware of the massive trouble he's about to face. "
        "The next morning, strange people arrive at his house asking about the girl. "
        "He realizes she is connected to a huge secret. "
        "To find the truth, he follows her and is taken to a desolate location. "
        "There he discovers a dangerous experiment that has been running secretly for years. "
        "But the biggest twist comes when he realizes his own past is deeply connected to it all. "
        "Now he must decide whether to run for his life, or end this mystery once and for all. "
        "From this point, the story takes a turn where the final truth leaves everyone in shock."
    )
    print(f"Text to synthesize: {text}")

    try:
        # The pipeline returns a generator.
        # Speed set to 1 and voice set to af_heart (American female)
        generator = pipeline(text, voice='af_heart', speed=1)
        
        # Collect all audio chunks because the script is long and will be split by the model
        audio_chunks = []
        for i, (gs, ps, audio) in enumerate(generator):
            audio_chunks.append(audio)
            
        import numpy as np
        if audio_chunks:
            final_audio = np.concatenate(audio_chunks)
            output_file = os.path.join(os.path.dirname(__file__), "test_english_recap.wav")
            print(f"Saving combined audio to {output_file}")
            sf.write(output_file, final_audio, 24000)
            print("Test generation complete.")
        else:
            print("No audio generated.")
            
    except Exception as e:
        print(f"Error generating audio: {e}")

if __name__ == "__main__":
    main()
