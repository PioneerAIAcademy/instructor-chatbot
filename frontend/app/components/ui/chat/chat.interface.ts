import { Message } from "ai";

export interface ChatHandler {
  messages: Message[];
  input: string;
  isLoading: boolean;
  handleSubmit: (
    e: React.FormEvent<HTMLFormElement>,
    ops?: {
      data?: any;
    },
  ) => void;
  handleInputChange: (e: React.ChangeEvent<HTMLInputElement>) => void;
  reload?: () => void;
  stop?: () => void;
  onFileUpload?: (file: File) => Promise<void>;
  onFileError?: (errMsg: string) => void;
  setInput?: React.Dispatch<React.SetStateAction<string>>;
  setMessages?: (messages: Message[]) => void;
  append?: (
    message: Message | Omit<Message, "id">,
    ops?: {
      data: any;
    },
  ) => Promise<string | null | undefined>;
}
